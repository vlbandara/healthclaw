from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.templating import Jinja2Templates

from nanobot.config.schema import Config
from nanobot.observability.metrics import onboarding_started_total
from nanobot.store.onboarding import PostgresOnboardingRepository, mint_signed_token
from nanobot.store.postgres import ensure_tenant_id


class TurnRequest(BaseModel):
    tenant_external_id: str = Field(..., description="Tenant external id (user id)")
    session_key: str = Field(..., description="Session key scoped to tenant (e.g. channel:chat_id)")
    channel: str = "api"
    chat_id: str = "default"
    content: str
    wait: bool = True
    stream: bool = False


class TurnResponse(BaseModel):
    request_id: str
    status: str
    content: str | None = None


class SignupSubmission(BaseModel):
    name: str = Field(min_length=1)
    timezone: str = "UTC"
    # landing.js sends resumeSetupToken; we accept it to preserve the existing contract.
    resume_setup_token: str = Field(default="", alias="resumeSetupToken")


class RedeemSubmission(BaseModel):
    token: str = Field(min_length=10)
    channel: str = "telegram"
    chat_id: str = Field(min_length=1)


class TelegramConnectSubmission(BaseModel):
    bot_token: str = Field(min_length=10, alias="botToken")


@dataclass(slots=True)
class GatewayState:
    config: Config
    redis_settings: RedisSettings
    limiter: Limiter
    pg_pool: asyncpg.Pool


def _require_api_key(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("NANOBOT_API_KEY", "").strip()
    if not expected:
        # If no key configured, allow (dev mode).
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid token")


def create_app(config: Config) -> FastAPI:
    limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    app = FastAPI(title="nanobot gateway", version="0.1")

    pg_pool: asyncpg.Pool | None = None
    templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "health" / "templates"))
    static_dir = Path(__file__).resolve().parents[1] / "health" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.on_event("startup")
    async def _startup() -> None:
        nonlocal pg_pool
        if not config.store.database_url:
            raise RuntimeError("config.store.database_url is required for gateway")
        pg_pool = await asyncpg.create_pool(dsn=config.store.database_url, min_size=1, max_size=10)
        app.state.gateway.pg_pool = pg_pool

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        nonlocal pg_pool
        if pg_pool is not None:
            await pg_pool.close()
            pg_pool = None

    app.state.gateway = GatewayState(
        config=config,
        redis_settings=RedisSettings.from_dsn(config.store.redis_url),
        limiter=limiter,
        pg_pool=None,  # set below once startup runs
    )

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def _attach_pool(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Ensure pool is present on state (defensive for tests).
        if pg_pool is not None and getattr(request.app.state.gateway, "pg_pool", None) is None:
            request.app.state.gateway.pg_pool = pg_pool
        return await call_next(request)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request, exc):  # type: ignore[no-untyped-def]
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/readyz")
    async def readyz() -> dict[str, Any]:
        # Lightweight check: can we connect to Redis?
        state: GatewayState = app.state.gateway
        pool = await create_pool(state.redis_settings)
        try:
            pong = await pool.ping()
            return {"ok": bool(pong)}
        finally:
            await pool.close()

    @app.get("/metrics")
    async def metrics():
        return StreamingResponse(
            iter([generate_latest()]),
            media_type=CONTENT_TYPE_LATEST,
        )

    # ---------------------------------------------------------------------
    # Healthclaw landing + onboarding (public)
    # ---------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def landing(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "landing.html", {})

    @app.post("/api/signup")
    @limiter.limit("30/minute")
    async def signup(request: Request, submission: SignupSubmission = Body(...)) -> JSONResponse:
        state: GatewayState = request.app.state.gateway
        repo = PostgresOnboardingRepository(state.pg_pool)
        try:
            token = mint_signed_token()
        except Exception as exc:
            # Make failure user-readable (landing.js displays `detail` on error).
            raise HTTPException(
                status_code=500,
                detail=f"Server is missing onboarding token secret (set NANOBOT_ONBOARDING_TOKEN_SECRET). ({exc})",
            ) from exc
        await repo.create_token(
            token=token,
            ttl=timedelta(hours=24),
            payload={"signup": {"name": submission.name, "timezone": submission.timezone}},
        )
        # Keep existing landing.js contract: setupToken + redirect to /setup/<token>
        return JSONResponse({"status": "ok", "setupToken": token, "userId": "", "resumed": False})

    @app.get("/setup/{setup_token}", response_class=HTMLResponse)
    async def setup_form(request: Request, setup_token: str) -> HTMLResponse:
        state: GatewayState = request.app.state.gateway
        repo = PostgresOnboardingRepository(state.pg_pool)
        payload = await repo.get_payload_any(token=setup_token) or {}
        saved_username = str(((payload.get("telegram") or {}) if isinstance(payload.get("telegram"), dict) else {}).get("bot_username") or "").strip()

        bot_username = (saved_username or os.environ.get("TELEGRAM_BOT_USERNAME", "")).strip().lstrip("@")
        telegram_link = (
            f"https://t.me/{bot_username}?start={setup_token}" if bot_username else ""
        )
        return templates.TemplateResponse(
            request,
            "onboard.html",
            {
                "invite": setup_token,
                "invite_meta": {"channel": "telegram"},
                "channel_links": {"telegram": telegram_link, "whatsapp": ""},
            },
        )

    @app.post("/api/onboard/{invite}/submit")
    @limiter.limit("30/minute")
    async def onboard_submit(request: Request, invite: str) -> JSONResponse:
        state: GatewayState = request.app.state.gateway
        payload = await request.json()
        repo = PostgresOnboardingRepository(state.pg_pool)
        await repo.update_payload(token=invite, payload={"web_onboard": payload})

        saved = await repo.get_payload_any(token=invite) or {}
        saved_username = str(((saved.get("telegram") or {}) if isinstance(saved.get("telegram"), dict) else {}).get("bot_username") or "").strip()
        bot_username = (saved_username or os.environ.get("TELEGRAM_BOT_USERNAME", "")).strip().lstrip("@")
        telegram_link = f"https://t.me/{bot_username}?start={invite}" if bot_username else ""
        return JSONResponse({"status": "ok", "channelLinks": {"telegram": telegram_link}, "userToken": ""})

    @app.post("/api/onboard/{invite}/channels/telegram")
    @limiter.limit("10/minute")
    async def onboard_connect_telegram(
        request: Request,
        invite: str,
        submission: TelegramConnectSubmission = Body(...),
    ) -> JSONResponse:
        state: GatewayState = request.app.state.gateway
        bot_token = submission.bot_token.strip()
        # Validate token via Telegram getMe
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            data = res.json()
        if not data.get("ok"):
            raise HTTPException(status_code=400, detail="Invalid Telegram bot token.")
        username = str(((data.get("result") or {}) if isinstance(data.get("result"), dict) else {}).get("username") or "").strip()
        if not username:
            raise HTTPException(status_code=400, detail="Telegram token validated but bot username missing.")

        repo = PostgresOnboardingRepository(state.pg_pool)
        await repo.update_payload(token=invite, payload={"telegram": {"bot_username": username}})

        telegram_link = f"https://t.me/{username}?start={invite}"
        return JSONResponse({"status": "ok", "telegram": {"bot_username": username}, "channelLinks": {"telegram": telegram_link}})

    @app.post("/v1/onboarding/redeem", dependencies=[Depends(_require_api_key)])
    async def redeem_onboarding(body: RedeemSubmission, request: Request) -> JSONResponse:
        state: GatewayState = request.app.state.gateway
        repo = PostgresOnboardingRepository(state.pg_pool)
        draft = await repo.get_payload(token=body.token) or {}
        result = await repo.redeem(token=body.token, channel=body.channel, chat_id=body.chat_id)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.detail)

        # Bind onboarding to the tenant derived from channel/chat_id.
        tenant_external_id = f"{body.channel}:{body.chat_id}"
        tenant_id = await ensure_tenant_id(state.pg_pool, tenant_external_id)
        session_key = tenant_external_id

        # Initialize onboarding state: draft from web (if any), still incomplete until tool call finalizes it.
        await repo.upsert_state(
            tenant_id=tenant_id,
            session_key=session_key,
            status="in_progress",
            phase="phase1",
            draft_submission=draft,
        )
        onboarding_started_total.labels(channel=body.channel).inc()
        return JSONResponse({"status": "ok", "tenant_external_id": tenant_external_id, "session_key": session_key})

    @app.post("/v1/turn", dependencies=[Depends(_require_api_key)])
    @limiter.limit("30/minute")
    async def submit_turn(request: Request, body: TurnRequest) -> TurnResponse:
        state: GatewayState = app.state.gateway
        request_id = str(uuid.uuid4())
        pool = await create_pool(state.redis_settings)
        try:
            job = await pool.enqueue_job(
                "process_turn",
                request_id=request_id,
                tenant_external_id=body.tenant_external_id,
                session_key=body.session_key,
                channel=body.channel,
                chat_id=body.chat_id,
                content=body.content,
            )
            if not body.wait:
                return TurnResponse(request_id=request_id, status="queued")
            if body.stream:
                # Client should use the streaming endpoint; we still wait for completion to return final content.
                pass
            result = await job.result(timeout=state.config.api.timeout)
            if isinstance(result, dict) and "content" in result:
                return TurnResponse(request_id=request_id, status="ok", content=str(result["content"]))
            return TurnResponse(request_id=request_id, status="ok", content=str(result))
        finally:
            await pool.close()

    @app.get("/v1/turn/stream/{request_id}", dependencies=[Depends(_require_api_key)])
    async def stream_turn(request_id: str):
        state: GatewayState = app.state.gateway
        channel = f"nanobot:stream:{request_id}"

        async def _gen():
            from redis.asyncio import Redis  # type: ignore

            r = Redis.from_url(state.config.store.redis_url, decode_responses=True)
            pubsub = r.pubsub()
            await pubsub.subscribe(channel)
            try:
                while True:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30.0)
                    if not msg:
                        continue
                    data = msg.get("data")
                    yield f"data: {data}\n\n"
                    try:
                        import json as _json

                        parsed = _json.loads(data)
                        if isinstance(parsed, dict) and parsed.get("type") == "end":
                            break
                    except Exception:
                        continue
            finally:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()
                except Exception:
                    pass
                await r.close()

        return StreamingResponse(_gen(), media_type="text/event-stream")

    return app

