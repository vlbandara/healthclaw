from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_secret() -> bytes:
    secret = os.environ.get("NANOBOT_ONBOARDING_TOKEN_SECRET", "").strip()
    if not secret:
        raise RuntimeError("NANOBOT_ONBOARDING_TOKEN_SECRET is required")
    return secret.encode("utf-8")


def mint_signed_token() -> str:
    """Create a signed token suitable for Telegram deep-links.

    Format: <nonce_b64url>.<sig_b64url> where sig = HMAC(secret, nonce).
    """
    nonce = secrets.token_bytes(24)
    secret = _require_secret()
    sig = hmac.new(secret, nonce, hashlib.sha256).digest()
    return f"{_b64url(nonce)}.{_b64url(sig)}"


def verify_signed_token(token: str) -> bool:
    try:
        nonce_b64, sig_b64 = (token or "").split(".", 1)
        nonce = _b64url_decode(nonce_b64)
        sig = _b64url_decode(sig_b64)
    except Exception:
        return False
    secret = _require_secret()
    expected = hmac.new(secret, nonce, hashlib.sha256).digest()
    return hmac.compare_digest(expected, sig)


@dataclass(slots=True)
class RedeemResult:
    ok: bool
    detail: str


class PostgresOnboardingRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def create_token(
        self,
        *,
        token: str,
        ttl: timedelta,
        payload: dict[str, Any] | None = None,
    ) -> None:
        token_hash = _hash_token(token)
        expires_at = _utcnow() + ttl
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO onboarding_tokens (token_hash, expires_at, payload)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (token_hash) DO NOTHING
                """,
                token_hash,
                expires_at,
                json.dumps(payload or {}, ensure_ascii=False),
            )

    async def _get_payload_row(self, *, token: str) -> tuple[dict[str, Any], datetime | None, datetime | None] | None:
        token_hash = _hash_token(token)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT payload, expires_at, redeemed_at
                FROM onboarding_tokens
                WHERE token_hash = $1
                """,
                token_hash,
            )
        if not row:
            return None
        payload = row["payload"] or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return payload, row["expires_at"], row["redeemed_at"]

    async def update_payload(self, *, token: str, payload: dict[str, Any]) -> None:
        """Merge payload into existing token payload (shallow dict merge)."""
        current = await self.get_payload_any(token=token)
        merged = dict(current or {})
        for k, v in (payload or {}).items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**(merged.get(k) or {}), **v}
            else:
                merged[k] = v
        token_hash = _hash_token(token)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE onboarding_tokens
                SET payload = $2::jsonb
                WHERE token_hash = $1
                """,
                token_hash,
                json.dumps(merged, ensure_ascii=False),
            )

    async def get_payload(self, *, token: str) -> dict[str, Any] | None:
        row = await self._get_payload_row(token=token)
        if not row:
            return None
        payload, expires_at, redeemed_at = row
        if redeemed_at is not None:
            return None
        if isinstance(expires_at, datetime) and expires_at < _utcnow():
            return None
        return payload

    async def get_payload_any(self, *, token: str) -> dict[str, Any] | None:
        """Get payload even if redeemed (still enforces expiry)."""
        row = await self._get_payload_row(token=token)
        if not row:
            return None
        payload, expires_at, _redeemed_at = row
        if isinstance(expires_at, datetime) and expires_at < _utcnow():
            return None
        return payload

    async def redeem(
        self,
        *,
        token: str,
        channel: str,
        chat_id: str,
    ) -> RedeemResult:
        if not verify_signed_token(token):
            return RedeemResult(ok=False, detail="invalid_token")

        token_hash = _hash_token(token)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT redeemed_at, expires_at
                FROM onboarding_tokens
                WHERE token_hash = $1
                """,
                token_hash,
            )
            if not row:
                return RedeemResult(ok=False, detail="token_not_found")
            if row["redeemed_at"] is not None:
                return RedeemResult(ok=False, detail="token_already_redeemed")
            expires_at = row["expires_at"]
            if isinstance(expires_at, datetime) and expires_at < _utcnow():
                return RedeemResult(ok=False, detail="token_expired")

            updated = await conn.execute(
                """
                UPDATE onboarding_tokens
                SET redeemed_at = now(),
                    redeemed_channel = $2,
                    redeemed_chat_id = $3
                WHERE token_hash = $1
                  AND redeemed_at IS NULL
                """,
                token_hash,
                channel,
                chat_id,
            )
        if "UPDATE 1" not in str(updated):
            return RedeemResult(ok=False, detail="token_redeem_race")
        return RedeemResult(ok=True, detail="ok")

    async def get_state(self, *, tenant_id: str, session_key: str) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT status, phase, draft_submission
                FROM onboarding_state
                WHERE tenant_id = $1::uuid AND session_key = $2
                """,
                tenant_id,
                session_key,
            )
        if not row:
            return None
        draft = row["draft_submission"] or {}
        if isinstance(draft, str):
            try:
                draft = json.loads(draft)
            except Exception:
                draft = {}
        return {
            "status": str(row["status"] or ""),
            "phase": str(row["phase"] or ""),
            "draft_submission": draft if isinstance(draft, dict) else {},
        }

    async def upsert_state(
        self,
        *,
        tenant_id: str,
        session_key: str,
        status: str,
        phase: str,
        draft_submission: dict[str, Any],
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO onboarding_state (tenant_id, session_key, status, phase, draft_submission, created_at, updated_at)
                VALUES ($1::uuid, $2, $3, $4, $5::jsonb, now(), now())
                ON CONFLICT (tenant_id, session_key) DO UPDATE SET
                    status = EXCLUDED.status,
                    phase = EXCLUDED.phase,
                    draft_submission = EXCLUDED.draft_submission,
                    updated_at = now()
                """,
                tenant_id,
                session_key,
                status,
                phase,
                json.dumps(draft_submission or {}, ensure_ascii=False),
            )

