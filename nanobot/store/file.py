from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.memory import MemoryStore
from nanobot.session.manager import Session, SessionManager
from nanobot.store.base import CheckpointRepository, MemoryHit, MemoryRepository, SessionRepository


def _normalize_memory_key(key: str) -> str:
    return str(key or "").strip().upper()


class FileSessionRepository(SessionRepository):
    """File-backed session repository (workspace JSONL).

    This is a compatibility adapter around the existing `SessionManager`.
    """

    def __init__(self, workspace: Path):
        self._sessions = SessionManager(workspace)

    async def get(self, tenant_id: str, session_key: str) -> Session:
        # tenant_id is ignored for file backend: workspace already scopes state.
        return self._sessions.get_or_create(session_key)

    async def save(self, tenant_id: str, session: Session) -> None:
        self._sessions.save(session)

    async def compact(self, tenant_id: str, session: Session) -> None:
        self._sessions.compact_session_file(session)


class FileCheckpointRepository(CheckpointRepository):
    """Stores checkpoints in the session metadata, mirroring current behavior."""

    def __init__(self, sessions: FileSessionRepository):
        self._sessions = sessions

    async def save(self, tenant_id: str, session_key: str, state: dict[str, Any]) -> None:
        session = await self._sessions.get(tenant_id, session_key)
        session.metadata["runtime_checkpoint"] = state
        await self._sessions.save(tenant_id, session)

    async def load(self, tenant_id: str, session_key: str) -> dict[str, Any] | None:
        session = await self._sessions.get(tenant_id, session_key)
        value = session.metadata.get("runtime_checkpoint")
        if isinstance(value, dict):
            return value
        return None

    async def clear(self, tenant_id: str, session_key: str) -> None:
        session = await self._sessions.get(tenant_id, session_key)
        if "runtime_checkpoint" in session.metadata:
            session.metadata.pop("runtime_checkpoint", None)
            await self._sessions.save(tenant_id, session)


class FileMemoryRepository(MemoryRepository):
    """Workspace-file-backed memory repository.

    Wraps current `MemoryStore` files (SOUL.md/USER.md/MEMORY.md/INTERESTS.md/history.jsonl).
    """

    def __init__(self, workspace: Path):
        self._store = MemoryStore(workspace)
        self._workspace = workspace

    def _doc_path(self, key: str) -> Path:
        k = _normalize_memory_key(key)
        if k in {"SOUL", "SOUL.MD"}:
            return self._store.soul_file
        if k in {"USER", "USER.MD"}:
            return self._store.user_file
        if k in {"MEMORY", "MEMORY.MD"}:
            return self._store.memory_file
        if k in {"INTERESTS", "INTERESTS.MD"}:
            return self._store.interest_file
        # Allow custom docs under memory/ by key name.
        safe = "".join(ch for ch in k if ch.isalnum() or ch in {"_", "-", "."}).strip("._-")
        if not safe:
            safe = "UNKNOWN"
        return self._workspace / "memory" / f"{safe}.md"

    async def get_document(self, tenant_id: str, key: str) -> str:
        path = self._doc_path(key)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    async def save_document(self, tenant_id: str, key: str, content: str) -> None:
        path = self._doc_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content or "", encoding="utf-8")

    async def add_memory(self, tenant_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        entry = {"content": content or "", "metadata": metadata or {}}
        self._store.history_file.parent.mkdir(parents=True, exist_ok=True)
        with self._store.history_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    async def search(self, tenant_id: str, query: str, limit: int = 5) -> list[MemoryHit]:
        q = (query or "").strip().lower()
        if not q:
            return []

        hits: list[MemoryHit] = []

        # 1) quick scan of core docs
        for key in ("SOUL", "USER", "MEMORY", "INTERESTS"):
            text = await self.get_document(tenant_id, key)
            if q in text.lower():
                hits.append(MemoryHit(key=key, content=text, score=1.0))
                if len(hits) >= limit:
                    return hits[:limit]

        # 2) scan history.jsonl, most recent first
        try:
            if not self._store.history_file.exists():
                return hits[:limit]
            lines = self._store.history_file.read_text(encoding="utf-8").splitlines()
            for line in reversed(lines):
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                text = str(data.get("content", "") or "")
                if q in text.lower():
                    hits.append(
                        MemoryHit(
                            key="HISTORY",
                            content=text,
                            score=0.5,
                            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else None,
                        )
                    )
                    if len(hits) >= limit:
                        break
        except Exception:
            logger.exception("FileMemoryRepository.search failed")

        return hits[:limit]

