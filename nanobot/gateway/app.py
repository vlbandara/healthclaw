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
from fastapi import Body, Cookie, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from nanobot.auth.middleware import RequestIdentity, make_auth_dependency
from nanobot.auth.passwords import verify_password
from nanobot.auth.repository import AuthRepository
from nanobot.auth.tokens import mint_session_token, verify_session_token
from nanobot.config.schema import Config
from nanobot.observability.metrics import onboarding_started_total
from nanobot.store.onboarding import PostgresOnboardingRepository, mint_signed_token
from nanobot.store.postgres import ensure_tenant_id


class TurnRequest(BaseModel):
    session_key: str = Field(..., description="Session key scoped to tenant")
    channel: str = "api"
    chat_id: str = "default"
    content: str
    wait: bool = True
    stream: bool = False


class ChannelMessageRequest(BaseModel):
    """Used by channel ingress services (telegram, whatsapp, etc.)."""
    channel: str
    chat_id: str
    content: str
    wait: bool = True


class TurnResponse(BaseModel):
    request_id: str
    status: str
    content: str | None = None


class SignupRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)
    timezone: str = "UTC"


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateApiKeyRequest(BaseModel):
    name: str = ""


class OnboardSignupSubmission(BaseModel):
    """Legacy onboarding flow submission (kept for existing landing page JS)."""
    name: str = Field(min_length=1)
    timezone: str = "UTC"
    resume_setup_token: str = Field(default="", alias="resumeSetupToken")


class RedeemSubmission(BaseModel):
    token: str = Field(min_length=10)
    channel: str = "telegram"
    chat_id: str = Field(min_length=1)


class TelegramConnectSubmission(BaseModel):
    bot_token: str = Field(min_length=10, alias="botToken")


class ChannelLinkStartRequest(BaseModel):
    channel: str = Field(min_length=1)


class ChannelLinkCompleteRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    channel: str
    external_id: str


class RedeemLinkRequest(BaseModel):
    token: str = Field(min_length=10)
    channel: str = "telegram"
    external_id: str = Field(min_length=1)


class AccountProfileRequest(BaseModel):
    phase1: dict = {}
    phase2: dict = {}


@dataclass(slots=True)
class GatewayState:
    config: Config
    redis_settings: RedisSettings
    limiter: Limiter
    pg_pool: asyncpg.Pool


def _require_system_api_key(authorization: str | None = Header(default=None)) -> None:
    """Validates the shared system API key (used by ingress services and internal calls)."""
    expected = os.environ.get("NANOBOT_API_KEY", "").strip()
    if not expected:
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
        pg_pool=None,
    )

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.middleware("http")
    async def _attach_pool(request: Request, call_next):  # type: ignore[no-untyped-def]
        if pg_pool is not None and getattr(request.app.state.gateway, "pg_pool", None) is None:
            request.app.state.gateway.pg_pool = pg_pool
        return await call_next(request)

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request, exc):  # type: ignore[no-untyped-def]
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    def _get_pool() -> asyncpg.Pool:
        pool = app.state.gateway.pg_pool
        if pool is None:
            raise HTTPException(status_code=503, detail="Database not ready")
        return pool

    auth_dep = make_auth_dependency(_get_pool)

    # -------------------------------------------------------------------------
    # Health / observability
    # -------------------------------------------------------------------------

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/readyz")
    async def readyz() -> dict[str, Any]:
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

    # -------------------------------------------------------------------------
    # Landing page
    # -------------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def landing(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "landing.html", {})

    # -------------------------------------------------------------------------
    # Auth: signup / login / logout
    # -------------------------------------------------------------------------

    @app.post("/api/auth/signup")
    @limiter.limit("10/minute")
    async def auth_signup(request: Request, body: SignupRequest = Body(...)) -> JSONResponse:
        pool = _get_pool()
        repo = AuthRepository(pool)
        existing = await repo.get_user_by_email(body.email)
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")
        user, raw_key = await repo.create_user(
            email=body.email,
            password=body.password,
            name=body.name,
            timezone=body.timezone,
        )
        session_token = mint_session_token(user.id, user.tenant_id)
        resp = JSONResponse({
            "status": "ok",
            "user": {"id": user.id, "email": user.email, "name": user.name},
            "apiKey": raw_key,
        })
        resp.set_cookie(
            "nanobot_session",
            session_token,
            httponly=True,
            samesite="lax",
            max_age=7 * 24 * 3600,
            secure=os.environ.get("NANOBOT_SECURE_COOKIES", "0") == "1",
        )
        return resp

    @app.post("/api/auth/login")
    @limiter.limit("20/minute")
    async def auth_login(request: Request, body: LoginRequest = Body(...)) -> JSONResponse:
        pool = _get_pool()
        repo = AuthRepository(pool)
        pw_hash = await repo.get_user_password_hash(body.email)
        if not pw_hash or not verify_password(pw_hash, body.password):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        user = await repo.get_user_by_email(body.email)
        assert user is not None
        await repo.touch_login(user.id)
        session_token = mint_session_token(user.id, user.tenant_id)
        resp = JSONResponse({"status": "ok", "user": {"id": user.id, "email": user.email, "name": user.name}})
        resp.set_cookie(
            "nanobot_session",
            session_token,
            httponly=True,
            samesite="lax",
            max_age=7 * 24 * 3600,
            secure=os.environ.get("NANOBOT_SECURE_COOKIES", "0") == "1",
        )
        return resp

    @app.post("/api/auth/logout")
    async def auth_logout() -> JSONResponse:
        resp = JSONResponse({"status": "ok"})
        resp.delete_cookie("nanobot_session")
        return resp

    # -------------------------------------------------------------------------
    # API key management
    # -------------------------------------------------------------------------

    @app.get("/api/keys")
    async def list_keys(identity: RequestIdentity = Depends(auth_dep)) -> JSONResponse:
        pool = _get_pool()
        repo = AuthRepository(pool)
        keys = await repo.list_api_keys(identity.user.id)
        return JSONResponse({
            "keys": [
                {
                    "id": k.id,
                    "prefix": k.prefix,
                    "name": k.name,
                    "created_at": k.created_at.isoformat(),
                    "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                    "revoked": k.revoked_at is not None,
                }
                for k in keys
            ]
        })

    @app.post("/api/keys")
    async def create_key(
        body: CreateApiKeyRequest = Body(...),
        identity: RequestIdentity = Depends(auth_dep),
    ) -> JSONResponse:
        pool = _get_pool()
        repo = AuthRepository(pool)
        raw_key, row = await repo.create_api_key(user_id=identity.user.id, name=body.name)
        return JSONResponse({
            "status": "ok",
            "key": raw_key,
            "id": row.id,
            "prefix": row.prefix,
            "name": row.name,
        })

    @app.delete("/api/keys/{key_id}")
    async def revoke_key(
        key_id: str,
        identity: RequestIdentity = Depends(auth_dep),
    ) -> JSONResponse:
        pool = _get_pool()
        repo = AuthRepository(pool)
        revoked = await repo.revoke_api_key(key_id=key_id, user_id=identity.user.id)
        if not revoked:
            raise HTTPException(status_code=404, detail="Key not found or already revoked")
        return JSONResponse({"status": "ok"})

    # -------------------------------------------------------------------------
    # Channel linking
    # -------------------------------------------------------------------------

    @app.post("/api/channels/link/start")
    async def channel_link_start(
        body: ChannelLinkStartRequest = Body(...),
        identity: RequestIdentity = Depends(auth_dep),
    ) -> JSONResponse:
        pool = _get_pool()
        repo = AuthRepository(pool)
        code = await repo.create_pairing_code(user_id=identity.user.id, channel=body.channel)
        return JSONResponse({"status": "ok", "code": code, "expires_in_seconds": 600})

    @app.post("/api/channels/link/complete", dependencies=[Depends(_require_system_api_key)])
    async def channel_link_complete(body: ChannelLinkCompleteRequest = Body(...)) -> JSONResponse:
        pool = _get_pool()
        repo = AuthRepository(pool)
        ok, detail = await repo.redeem_pairing_code(code=body.code, external_id=body.external_id)
        if not ok:
            raise HTTPException(status_code=400, detail=detail)
        return JSONResponse({"status": "ok"})

    @app.get("/api/channels")
    async def list_channels(identity: RequestIdentity = Depends(auth_dep)) -> JSONResponse:
        pool = _get_pool()
        repo = AuthRepository(pool)
        links = await repo.list_channel_links(identity.user.id)
        return JSONResponse({
            "links": [
                {
                    "id": lk.id,
                    "channel": lk.channel,
                    "external_id": lk.external_id,
                    "created_at": lk.created_at.isoformat(),
                }
                for lk in links
            ]
        })

    # -------------------------------------------------------------------------
    # Legacy onboarding surface (kept for existing landing page JS)
    # -------------------------------------------------------------------------

    @app.post("/api/signup")
    @limiter.limit("30/minute")
    async def signup(request: Request, submission: OnboardSignupSubmission = Body(...)) -> JSONResponse:
        state: GatewayState = request.app.state.gateway
        repo = PostgresOnboardingRepository(state.pg_pool)
        try:
            token = mint_signed_token()
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Server is missing onboarding token secret (set NANOBOT_ONBOARDING_TOKEN_SECRET). ({exc})",
            ) from exc
        await repo.create_token(
            token=token,
            ttl=timedelta(hours=24),
            payload={"signup": {"name": submission.name, "timezone": submission.timezone}},
        )
        return JSONResponse({"status": "ok", "setupToken": token, "userId": "", "resumed": False})

    @app.get("/setup/{setup_token}", response_class=HTMLResponse)
    async def setup_form(request: Request, setup_token: str) -> HTMLResponse:
        state: GatewayState = request.app.state.gateway
        repo = PostgresOnboardingRepository(state.pg_pool)
        payload = await repo.get_payload_any(token=setup_token) or {}
        saved_username = str(((payload.get("telegram") or {}) if isinstance(payload.get("telegram"), dict) else {}).get("bot_username") or "").strip()
        bot_username = (saved_username or os.environ.get("TELEGRAM_BOT_USERNAME", "")).strip().lstrip("@")
        telegram_link = f"https://t.me/{bot_username}?start={setup_token}" if bot_username else ""
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

    @app.post("/v1/onboarding/redeem", dependencies=[Depends(_require_system_api_key)])
    async def redeem_onboarding(body: RedeemSubmission, request: Request) -> JSONResponse:
        state: GatewayState = request.app.state.gateway
        repo = PostgresOnboardingRepository(state.pg_pool)
        draft = await repo.get_payload(token=body.token) or {}
        result = await repo.redeem(token=body.token, channel=body.channel, chat_id=body.chat_id)
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.detail)
        tenant_external_id = f"{body.channel}:{body.chat_id}"
        tenant_id = await ensure_tenant_id(state.pg_pool, tenant_external_id)
        session_key = tenant_external_id
        await repo.upsert_state(
            tenant_id=tenant_id,
            session_key=session_key,
            status="in_progress",
            phase="phase1",
            draft_submission=draft,
        )
        onboarding_started_total.labels(channel=body.channel).inc()
        return JSONResponse({"status": "ok", "tenant_external_id": tenant_external_id, "session_key": session_key})

    # -------------------------------------------------------------------------
    # Turn API (authenticated via user API key or session)
    # -------------------------------------------------------------------------

    @app.post("/v1/turn")
    @limiter.limit("30/minute")
    async def submit_turn(
        request: Request,
        body: TurnRequest,
        identity: RequestIdentity = Depends(auth_dep),
    ) -> TurnResponse:
        state: GatewayState = app.state.gateway
        request_id = str(uuid.uuid4())
        pool = await create_pool(state.redis_settings)
        try:
            job = await pool.enqueue_job(
                "process_turn",
                request_id=request_id,
                tenant_external_id=identity.tenant_id,
                session_key=body.session_key,
                channel=body.channel,
                chat_id=body.chat_id,
                content=body.content,
            )
            if not body.wait:
                return TurnResponse(request_id=request_id, status="queued")
            result = await job.result(timeout=state.config.api.timeout)
            if isinstance(result, dict) and "content" in result:
                return TurnResponse(request_id=request_id, status="ok", content=str(result["content"]))
            return TurnResponse(request_id=request_id, status="ok", content=str(result))
        finally:
            await pool.close()

    # -------------------------------------------------------------------------
    # Channel message endpoint (used by telegram/whatsapp ingress services)
    # -------------------------------------------------------------------------

    @app.post("/v1/channel/message", dependencies=[Depends(_require_system_api_key)])
    @limiter.limit("60/minute")
    async def channel_message(
        request: Request,
        body: ChannelMessageRequest,
    ) -> JSONResponse:
        """Route an inbound channel message to the correct tenant via channel_links."""
        state: GatewayState = app.state.gateway
        pool = _get_pool()
        repo = AuthRepository(pool)

        tenant_id = await repo.resolve_tenant_for_channel(body.channel, body.chat_id)
        if not tenant_id:
            signup_url = os.environ.get("HEALTHCLAW_SIGNUP_URL", "http://localhost:8080/signup")
            return JSONResponse(
                {
                    "content": (
                        f"This Telegram chat isn't linked to any Healthclaw account.\n\n"
                        f"Sign up at {signup_url}, then go to your account page and click "
                        f"\"Link Telegram\" to connect this chat."
                    )
                },
                status_code=200,
            )

        request_id = str(uuid.uuid4())
        redis_pool = await create_pool(state.redis_settings)
        try:
            job = await redis_pool.enqueue_job(
                "process_turn",
                request_id=request_id,
                tenant_external_id=tenant_id,
                session_key=f"{body.channel}:{body.chat_id}",
                channel=body.channel,
                chat_id=body.chat_id,
                content=body.content,
            )
            if not body.wait:
                return JSONResponse({"status": "queued", "request_id": request_id})
            result = await job.result(timeout=state.config.api.timeout)
            content = result.get("content") if isinstance(result, dict) else str(result)
            return JSONResponse({"status": "ok", "content": str(content or "")})
        finally:
            await redis_pool.close()

    @app.get("/v1/turn/stream/{request_id}", dependencies=[Depends(_require_system_api_key)])
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

    # -------------------------------------------------------------------------
    # UI page routes
    # -------------------------------------------------------------------------

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "login.html", {})

    @app.get("/signup", response_class=HTMLResponse)
    async def signup_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "signup.html", {})

    @app.get("/account", response_class=HTMLResponse)
    async def account_page(
        request: Request,
        nanobot_session: str | None = Cookie(default=None),
    ) -> HTMLResponse:
        from starlette.responses import RedirectResponse

        claims = verify_session_token(nanobot_session or "")
        if not claims:
            return RedirectResponse(url="/login", status_code=302)

        pool = _get_pool()
        repo = AuthRepository(pool)
        user = await repo.get_user_by_id(claims.user_id)
        if not user:
            return RedirectResponse(url="/login", status_code=302)

        links = await repo.list_channel_links(user.id)
        telegram_link = next(
            (lk for lk in links if lk.channel == "telegram"), None
        )
        bot_username = ""
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT config FROM tenants WHERE id = $1::uuid", user.tenant_id
            )
            if row:
                cfg = row["config"] or {}
                if isinstance(cfg, str):
                    import json as _json
                    cfg = _json.loads(cfg)
                bot_username = str((cfg or {}).get("telegram_bot_username", ""))
        # Fall back to system-wide env var (the shared bot used in new flow)
        if not bot_username:
            bot_username = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")

        return templates.TemplateResponse(request, "account.html", {
            "user": {"id": user.id, "email": user.email, "name": user.name, "timezone": user.timezone},
            "telegram_linked": telegram_link is not None,
            "telegram_chat_id": telegram_link.external_id if telegram_link else "",
            "bot_username": bot_username,
        })

    # -------------------------------------------------------------------------
    # Account API endpoints (authenticated)
    # -------------------------------------------------------------------------

    @app.post("/api/account/telegram/generate-link")
    @limiter.limit("10/minute")
    async def account_telegram_generate_link(
        request: Request,
        identity: RequestIdentity = Depends(auth_dep),
    ) -> JSONResponse:
        """Generate a one-time Telegram deep-link for the authenticated user.

        Returns a t.me URL. When the user clicks it, Telegram opens and sends
        /start <token> to the bot. The ingress redeems the token and links
        that specific chat_id to this account — nobody else can link.
        """
        bot_username = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
        if not bot_username:
            raise HTTPException(
                status_code=503,
                detail="TELEGRAM_BOT_USERNAME is not configured on this server.",
            )
        pool = _get_pool()
        repo = AuthRepository(pool)
        token = await repo.create_link_token(user_id=identity.user.id, channel="telegram")
        deep_link = f"https://t.me/{bot_username}?start={token}"
        return JSONResponse({
            "status": "ok",
            "deep_link": deep_link,
            "bot_username": bot_username,
            "expires_in_seconds": 900,
        })

    @app.post("/v1/channel/redeem-link", dependencies=[Depends(_require_system_api_key)])
    async def channel_redeem_link(body: RedeemLinkRequest) -> JSONResponse:
        """Called by the telegram ingress when a user sends /start <token>.

        Validates the one-time token and links the chat_id to the account.
        Rejects if token is expired, already used, or not found.
        """
        pool = _get_pool()
        repo = AuthRepository(pool)
        ok, detail = await repo.redeem_link_token(
            token=body.token, external_id=body.external_id
        )
        if not ok:
            raise HTTPException(status_code=400, detail=detail)
        return JSONResponse({"status": "ok"})

    @app.post("/api/account/profile")
    async def account_save_profile(
        body: AccountProfileRequest = Body(...),
        identity: RequestIdentity = Depends(auth_dep),
    ) -> JSONResponse:
        """Persist care-preferences profile to the tenant workspace."""
        import json as _json
        pool = _get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT config FROM tenants WHERE id = $1::uuid", identity.tenant_id
            )
            existing_cfg: dict = {}
            if row and row["config"]:
                raw = row["config"]
                existing_cfg = raw if isinstance(raw, dict) else _json.loads(raw)
            existing_cfg["profile"] = {"phase1": body.phase1, "phase2": body.phase2}
            await conn.execute(
                "UPDATE tenants SET config = $1::jsonb WHERE id = $2::uuid",
                _json.dumps(existing_cfg),
                identity.tenant_id,
            )
        return JSONResponse({"status": "ok"})

    return app
