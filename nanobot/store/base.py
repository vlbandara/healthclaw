from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from nanobot.session.manager import Session


@dataclass(frozen=True, slots=True)
class MemoryHit:
    key: str
    content: str
    score: float | None = None
    metadata: dict[str, Any] | None = None


class SessionRepository(Protocol):
    async def get(self, tenant_id: str, session_key: str) -> Session: ...
    async def save(self, tenant_id: str, session: Session) -> None: ...
    async def compact(self, tenant_id: str, session: Session) -> None: ...


class MemoryRepository(Protocol):
    async def get_document(self, tenant_id: str, key: str) -> str: ...
    async def save_document(self, tenant_id: str, key: str, content: str) -> None: ...

    async def search(self, tenant_id: str, query: str, limit: int = 5) -> list[MemoryHit]: ...
    async def add_memory(self, tenant_id: str, content: str, metadata: dict[str, Any] | None = None) -> None: ...


class CheckpointRepository(Protocol):
    async def save(self, tenant_id: str, session_key: str, state: dict[str, Any]) -> None: ...
    async def load(self, tenant_id: str, session_key: str) -> dict[str, Any] | None: ...
    async def clear(self, tenant_id: str, session_key: str) -> None: ...

