from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
from loguru import logger

from nanobot.session.manager import Session
from nanobot.store.base import CheckpointRepository, MemoryHit, MemoryRepository, SessionRepository


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PostgresStoreConfig:
    database_url: str
    min_pool_size: int = 1
    max_pool_size: int = 10


class PostgresPool:
    def __init__(self, cfg: PostgresStoreConfig):
        self._cfg = cfg
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                dsn=self._cfg.database_url,
                min_size=self._cfg.min_pool_size,
                max_size=self._cfg.max_pool_size,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def acquire(self) -> asyncpg.Connection:
        pool = await self.init()
        return await pool.acquire()


async def ensure_tenant_id(pool: asyncpg.Pool, external_id: str) -> str:
    """Return tenant UUID string for an external_id, creating if needed."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO tenants (external_id, last_active_at)
            VALUES ($1, now())
            ON CONFLICT (external_id) DO UPDATE SET last_active_at = now()
            RETURNING id;
            """,
            external_id,
        )
        return str(row["id"])


class PostgresSessionRepository(SessionRepository):
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get(self, tenant_id: str, session_key: str) -> Session:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT messages, metadata, last_consolidated, created_at, updated_at
                FROM sessions
                WHERE tenant_id = $1::uuid AND session_key = $2
                """,
                tenant_id,
                session_key,
            )
            if not row:
                session = Session(key=session_key)
                await self.save(tenant_id, session)
                return session

            messages = row["messages"] or []
            metadata = row["metadata"] or {}
            last_consolidated = int(row["last_consolidated"] or 0)
            created_at = row["created_at"] or _utcnow()
            updated_at = row["updated_at"] or _utcnow()

            if isinstance(messages, str):
                messages = json.loads(messages)
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            return Session(
                key=session_key,
                messages=list(messages) if isinstance(messages, list) else [],
                metadata=dict(metadata) if isinstance(metadata, dict) else {},
                last_consolidated=last_consolidated,
                created_at=created_at,
                updated_at=updated_at,
            )

    async def save(self, tenant_id: str, session: Session) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (tenant_id, session_key, messages, metadata, last_consolidated, created_at, updated_at)
                VALUES ($1::uuid, $2, $3::jsonb, $4::jsonb, $5, $6, $7)
                ON CONFLICT (tenant_id, session_key) DO UPDATE SET
                    messages = EXCLUDED.messages,
                    metadata = EXCLUDED.metadata,
                    last_consolidated = EXCLUDED.last_consolidated,
                    updated_at = EXCLUDED.updated_at
                """,
                tenant_id,
                session.key,
                json.dumps(session.messages, ensure_ascii=False),
                json.dumps(session.metadata, ensure_ascii=False),
                int(session.last_consolidated),
                session.created_at,
                session.updated_at,
            )

    async def compact(self, tenant_id: str, session: Session) -> None:
        # Compact is a session-level transformation; callers should already have updated `session`.
        await self.save(tenant_id, session)


class PostgresCheckpointRepository(CheckpointRepository):
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def save(self, tenant_id: str, session_key: str, state: dict[str, Any]) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO checkpoints (tenant_id, session_key, state, updated_at)
                VALUES ($1::uuid, $2, $3::jsonb, now())
                ON CONFLICT (tenant_id, session_key) DO UPDATE SET
                    state = EXCLUDED.state,
                    updated_at = now()
                """,
                tenant_id,
                session_key,
                json.dumps(state, ensure_ascii=False),
            )

    async def load(self, tenant_id: str, session_key: str) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT state FROM checkpoints
                WHERE tenant_id = $1::uuid AND session_key = $2
                """,
                tenant_id,
                session_key,
            )
            if not row:
                return None
            state = row["state"]
            if isinstance(state, dict):
                return state
            if isinstance(state, str):
                return json.loads(state)
            return None

    async def clear(self, tenant_id: str, session_key: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM checkpoints WHERE tenant_id = $1::uuid AND session_key = $2",
                tenant_id,
                session_key,
            )


class PostgresMemoryRepository(MemoryRepository):
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_document(self, tenant_id: str, key: str) -> str:
        k = str(key or "").strip().upper()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT content FROM memory_documents
                WHERE tenant_id = $1::uuid AND key = $2
                """,
                tenant_id,
                k,
            )
            return str(row["content"]) if row else ""

    async def save_document(self, tenant_id: str, key: str, content: str) -> None:
        k = str(key or "").strip().upper()
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_documents (tenant_id, key, content, updated_at)
                VALUES ($1::uuid, $2, $3, now())
                ON CONFLICT (tenant_id, key) DO UPDATE SET
                    content = EXCLUDED.content,
                    version = memory_documents.version + 1,
                    updated_at = now()
                """,
                tenant_id,
                k,
                content or "",
            )

    async def add_memory(self, tenant_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        # Embedding is handled by mem0 or an external embedder; keep nullable for now.
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_history (tenant_id, content, summary, embedding, created_at)
                VALUES ($1::uuid, $2, NULL, NULL, now())
                """,
                tenant_id,
                content or "",
            )
        if metadata:
            logger.debug("PostgresMemoryRepository.add_memory metadata ignored (mem0 phase will use it)")

    async def search(self, tenant_id: str, query: str, limit: int = 5) -> list[MemoryHit]:
        q = (query or "").strip()
        if not q:
            return []
        # Placeholder search: fallback to simple LIKE on content/summary.
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT content, summary, created_at
                FROM memory_history
                WHERE tenant_id = $1::uuid
                  AND (content ILIKE '%' || $2 || '%' OR coalesce(summary,'') ILIKE '%' || $2 || '%')
                ORDER BY created_at DESC
                LIMIT $3
                """,
                tenant_id,
                q,
                int(limit),
            )
        return [MemoryHit(key="HISTORY", content=str(r["summary"] or r["content"]), score=None) for r in rows]

