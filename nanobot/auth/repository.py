from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from nanobot.auth.passwords import hash_password
from nanobot.auth.tokens import hash_api_key, mint_api_key, mint_link_token, mint_pairing_code


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class UserRow:
    id: str
    email: str
    name: str
    timezone: str
    tenant_id: str
    created_at: datetime
    last_login_at: datetime | None


@dataclass(slots=True)
class ApiKeyRow:
    id: str
    user_id: str
    prefix: str
    name: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


@dataclass(slots=True)
class ChannelLinkRow:
    id: str
    user_id: str
    channel: str
    external_id: str
    created_at: datetime


class AuthRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def create_user(
        self,
        *,
        email: str,
        password: str,
        name: str,
        timezone: str = "UTC",
    ) -> tuple[UserRow, str]:
        """Create a tenant + user. Returns (user, first_api_key_raw)."""
        pw_hash = hash_password(password)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                tenant_row = await conn.fetchrow(
                    """
                    INSERT INTO tenants (external_id)
                    VALUES ($1)
                    RETURNING id
                    """,
                    f"user:{email}",
                )
                tenant_id = str(tenant_row["id"])

                user_row = await conn.fetchrow(
                    """
                    INSERT INTO users (email, password_hash, name, timezone, tenant_id)
                    VALUES ($1, $2, $3, $4, $5::uuid)
                    RETURNING id, email, name, timezone, tenant_id, created_at, last_login_at
                    """,
                    email.lower().strip(),
                    pw_hash,
                    name.strip(),
                    timezone.strip() or "UTC",
                    tenant_id,
                )
                raw_key, key_hash, prefix = mint_api_key()
                await conn.execute(
                    """
                    INSERT INTO api_keys (user_id, key_hash, prefix, name)
                    VALUES ($1::uuid, $2, $3, $4)
                    """,
                    str(user_row["id"]),
                    key_hash,
                    prefix,
                    "default",
                )

        return UserRow(
            id=str(user_row["id"]),
            email=str(user_row["email"]),
            name=str(user_row["name"]),
            timezone=str(user_row["timezone"]),
            tenant_id=str(user_row["tenant_id"]),
            created_at=user_row["created_at"],
            last_login_at=user_row["last_login_at"],
        ), raw_key

    async def get_user_by_email(self, email: str) -> UserRow | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, email, name, timezone, tenant_id, created_at, last_login_at
                FROM users WHERE email = $1
                """,
                email.lower().strip(),
            )
        if not row:
            return None
        return UserRow(
            id=str(row["id"]),
            email=str(row["email"]),
            name=str(row["name"]),
            timezone=str(row["timezone"]),
            tenant_id=str(row["tenant_id"]),
            created_at=row["created_at"],
            last_login_at=row["last_login_at"],
        )

    async def get_user_password_hash(self, email: str) -> str | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT password_hash FROM users WHERE email = $1",
                email.lower().strip(),
            )
        return str(row["password_hash"]) if row else None

    async def touch_login(self, user_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET last_login_at = now() WHERE id = $1::uuid",
                user_id,
            )

    # ------------------------------------------------------------------
    # API keys
    # ------------------------------------------------------------------

    async def create_api_key(self, *, user_id: str, name: str = "") -> tuple[str, ApiKeyRow]:
        """Returns (raw_key, row)."""
        raw_key, key_hash, prefix = mint_api_key()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO api_keys (user_id, key_hash, prefix, name)
                VALUES ($1::uuid, $2, $3, $4)
                RETURNING id, user_id, prefix, name, created_at, last_used_at, revoked_at
                """,
                user_id,
                key_hash,
                prefix,
                (name or "").strip(),
            )
        return raw_key, ApiKeyRow(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            prefix=str(row["prefix"]),
            name=str(row["name"]),
            created_at=row["created_at"],
            last_used_at=row["last_used_at"],
            revoked_at=row["revoked_at"],
        )

    async def verify_api_key(self, raw_key: str) -> UserRow | None:
        """Return user if key is valid and not revoked, else None. Also touches last_used_at."""
        key_hash = hash_api_key(raw_key)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT ak.id AS key_id, u.id, u.email, u.name, u.timezone, u.tenant_id,
                       u.created_at, u.last_login_at
                FROM api_keys ak
                JOIN users u ON u.id = ak.user_id
                WHERE ak.key_hash = $1 AND ak.revoked_at IS NULL
                """,
                key_hash,
            )
            if not row:
                return None
            await conn.execute(
                "UPDATE api_keys SET last_used_at = now() WHERE id = $1::uuid",
                str(row["key_id"]),
            )
        return UserRow(
            id=str(row["id"]),
            email=str(row["email"]),
            name=str(row["name"]),
            timezone=str(row["timezone"]),
            tenant_id=str(row["tenant_id"]),
            created_at=row["created_at"],
            last_login_at=row["last_login_at"],
        )

    async def list_api_keys(self, user_id: str) -> list[ApiKeyRow]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, prefix, name, created_at, last_used_at, revoked_at
                FROM api_keys WHERE user_id = $1::uuid
                ORDER BY created_at DESC
                """,
                user_id,
            )
        return [
            ApiKeyRow(
                id=str(r["id"]),
                user_id=str(r["user_id"]),
                prefix=str(r["prefix"]),
                name=str(r["name"]),
                created_at=r["created_at"],
                last_used_at=r["last_used_at"],
                revoked_at=r["revoked_at"],
            )
            for r in rows
        ]

    async def revoke_api_key(self, *, key_id: str, user_id: str) -> bool:
        """Revoke a key belonging to the given user. Returns True if revoked."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE api_keys SET revoked_at = now()
                WHERE id = $1::uuid AND user_id = $2::uuid AND revoked_at IS NULL
                """,
                key_id,
                user_id,
            )
        return "UPDATE 1" in str(result)

    # ------------------------------------------------------------------
    # Channel links
    # ------------------------------------------------------------------

    async def resolve_tenant_for_channel(self, channel: str, external_id: str) -> str | None:
        """Return tenant_id for a linked channel, or None if not linked."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.tenant_id FROM channel_links cl
                JOIN users u ON u.id = cl.user_id
                WHERE cl.channel = $1 AND cl.external_id = $2
                """,
                channel,
                external_id,
            )
        return str(row["tenant_id"]) if row else None

    async def list_channel_links(self, user_id: str) -> list[ChannelLinkRow]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, user_id, channel, external_id, created_at
                FROM channel_links WHERE user_id = $1::uuid
                ORDER BY created_at DESC
                """,
                user_id,
            )
        return [
            ChannelLinkRow(
                id=str(r["id"]),
                user_id=str(r["user_id"]),
                channel=str(r["channel"]),
                external_id=str(r["external_id"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    async def create_pairing_code(self, *, user_id: str, channel: str) -> str:
        """Create a 6-digit pairing code for channel linking. Returns the code."""
        code = mint_pairing_code()
        expires_at = _utcnow() + timedelta(minutes=10)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO channel_pairing_codes (code, user_id, channel, expires_at)
                VALUES ($1, $2::uuid, $3, $4)
                ON CONFLICT (code) DO UPDATE
                  SET user_id = EXCLUDED.user_id,
                      channel = EXCLUDED.channel,
                      expires_at = EXCLUDED.expires_at,
                      redeemed_at = NULL
                """,
                code,
                user_id,
                channel,
                expires_at,
            )
        return code

    async def redeem_pairing_code(
        self, *, code: str, external_id: str
    ) -> tuple[bool, str]:
        """Try to redeem a pairing code. Returns (ok, detail)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, channel, expires_at, redeemed_at
                FROM channel_pairing_codes WHERE code = $1
                """,
                code,
            )
            if not row:
                return False, "code_not_found"
            if row["redeemed_at"] is not None:
                return False, "code_already_redeemed"
            if row["expires_at"] < _utcnow():
                return False, "code_expired"

            async with conn.transaction():
                await conn.execute(
                    "UPDATE channel_pairing_codes SET redeemed_at = now() WHERE code = $1",
                    code,
                )
                await conn.execute(
                    """
                    INSERT INTO channel_links (user_id, channel, external_id)
                    VALUES ($1::uuid, $2, $3)
                    ON CONFLICT (channel, external_id) DO NOTHING
                    """,
                    str(row["user_id"]),
                    str(row["channel"]),
                    external_id,
                )
        return True, "ok"

    async def create_link_token(self, *, user_id: str, channel: str) -> str:
        """Create a one-time deep-link token (15-minute TTL). Returns raw token."""
        token = mint_link_token()
        expires_at = _utcnow() + timedelta(minutes=15)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO channel_pairing_codes (code, user_id, channel, expires_at)
                VALUES ($1, $2::uuid, $3, $4)
                """,
                token,
                user_id,
                channel,
                expires_at,
            )
        return token

    async def redeem_link_token(
        self, *, token: str, external_id: str
    ) -> tuple[bool, str]:
        """Redeem a deep-link token (sent via /start).

        Returns (ok, detail). On success, creates the channel_link.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT user_id, channel, expires_at, redeemed_at
                FROM channel_pairing_codes WHERE code = $1
                """,
                token,
            )
            if not row:
                return False, "token_not_found"
            if row["redeemed_at"] is not None:
                return False, "token_already_used"
            if row["expires_at"] < _utcnow():
                return False, "token_expired"

            async with conn.transaction():
                await conn.execute(
                    "UPDATE channel_pairing_codes SET redeemed_at = now() WHERE code = $1",
                    token,
                )
                await conn.execute(
                    """
                    INSERT INTO channel_links (user_id, channel, external_id)
                    VALUES ($1::uuid, $2, $3)
                    ON CONFLICT (channel, external_id) DO UPDATE
                        SET user_id = EXCLUDED.user_id
                    """,
                    str(row["user_id"]),
                    str(row["channel"]),
                    external_id,
                )
        return True, "ok"

    async def get_user_by_id(self, user_id: str) -> UserRow | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, email, name, timezone, tenant_id, created_at, last_login_at
                FROM users WHERE id = $1::uuid
                """,
                user_id,
            )
        if not row:
            return None
        return UserRow(
            id=str(row["id"]),
            email=str(row["email"]),
            name=str(row["name"]),
            timezone=str(row["timezone"]),
            tenant_id=str(row["tenant_id"]),
            created_at=row["created_at"],
            last_login_at=row["last_login_at"],
        )
