from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from nanobot.config.schema import Config


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


@dataclass(slots=True)
class GatewayState:
    config: Config
    redis_settings: RedisSettings
    limiter: Limiter


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

    app.state.gateway = GatewayState(
        config=config,
        redis_settings=RedisSettings.from_dsn(config.store.redis_url),
        limiter=limiter,
    )

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

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
            pool.close()
            await pool.wait_closed()

    @app.get("/metrics")
    async def metrics():
        return StreamingResponse(
            iter([generate_latest()]),
            media_type=CONTENT_TYPE_LATEST,
        )

    @app.post("/v1/turn", dependencies=[Depends(_require_api_key)])
    @limiter.limit("30/minute")
    async def submit_turn(body: TurnRequest) -> TurnResponse:
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
            pool.close()
            await pool.wait_closed()

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

