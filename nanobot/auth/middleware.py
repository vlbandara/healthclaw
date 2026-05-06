from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import asyncpg
from fastapi import Cookie, Header, HTTPException, Request

from nanobot.auth.repository import AuthRepository, UserRow
from nanobot.auth.tokens import verify_session_token


@dataclass(slots=True)
class RequestIdentity:
    user: UserRow
    tenant_id: str
    source: Literal["api_key", "session"]


async def _resolve_identity(
    pool: asyncpg.Pool,
    authorization: str | None,
    session_token: str | None,
) -> RequestIdentity:
    repo = AuthRepository(pool)

    if authorization and authorization.lower().startswith("bearer nb_live_"):
        raw_key = authorization.split(" ", 1)[1].strip()
        user = await repo.verify_api_key(raw_key)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        return RequestIdentity(user=user, tenant_id=user.tenant_id, source="api_key")

    if session_token:
        claims = verify_session_token(session_token)
        if not claims:
            raise HTTPException(status_code=401, detail="Session expired or invalid")
        user = await repo.get_user_by_id(claims.user_id)
        if not user:
            raise HTTPException(status_code=401, detail="Session refers to deleted user")
        return RequestIdentity(user=user, tenant_id=user.tenant_id, source="session")

    raise HTTPException(status_code=401, detail="Authentication required")


def make_auth_dependency(get_pool):
    """Return a FastAPI dependency that resolves RequestIdentity from request."""

    async def auth_dep(
        request: Request,
        authorization: str | None = Header(default=None),
        nanobot_session: str | None = Cookie(default=None),
    ) -> RequestIdentity:
        pool: asyncpg.Pool = get_pool()
        identity = await _resolve_identity(pool, authorization, nanobot_session)
        request.state.identity = identity
        return identity

    return auth_dep
