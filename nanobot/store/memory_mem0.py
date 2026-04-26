from __future__ import annotations

from typing import Any

from loguru import logger

from nanobot.store.base import MemoryHit, MemoryRepository


class Mem0MemoryRepository(MemoryRepository):
    """Mem0-backed semantic memory for `search()` and `add_memory()`.

    This adapter composes an existing document repository for `get_document()` / `save_document()`
    (e.g. Postgres or file backend) while delegating semantic memory operations to mem0.
    """

    def __init__(
        self,
        *,
        documents: MemoryRepository,
        mem0_config: dict[str, Any] | None = None,
    ):
        self._documents = documents
        self._mem0_config = mem0_config or {}
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from mem0 import Memory  # type: ignore

            self._client = Memory.from_config(self._mem0_config) if self._mem0_config else Memory()
            return self._client
        except Exception as exc:
            raise RuntimeError(f"mem0 initialization failed: {exc}") from exc

    async def get_document(self, tenant_id: str, key: str) -> str:
        return await self._documents.get_document(tenant_id, key)

    async def save_document(self, tenant_id: str, key: str, content: str) -> None:
        await self._documents.save_document(tenant_id, key, content)

    async def add_memory(self, tenant_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        mem = self._get_client()
        try:
            # mem0 expects messages (role/content) or raw strings; we store as a single user message.
            messages = [{"role": "user", "content": content or ""}]
            mem.add(messages, user_id=str(tenant_id), metadata=metadata or {})
        except TypeError:
            # Back-compat for older mem0: no metadata kwarg.
            mem.add([{"role": "user", "content": content or ""}], user_id=str(tenant_id))
        except Exception:
            logger.exception("mem0 add_memory failed")
            # Don't fail the turn for memory issues (production hardening: make it best-effort).
            return

    async def search(self, tenant_id: str, query: str, limit: int = 5) -> list[MemoryHit]:
        mem = self._get_client()
        try:
            res = mem.search(query or "", filters={"user_id": str(tenant_id)})
            results = (res or {}).get("results") if isinstance(res, dict) else res
            hits: list[MemoryHit] = []
            if isinstance(results, list):
                for item in results[: max(0, int(limit))]:
                    if not isinstance(item, dict):
                        continue
                    hits.append(
                        MemoryHit(
                            key=str(item.get("id") or "mem0"),
                            content=str(item.get("memory") or ""),
                            score=float(item["score"]) if "score" in item and item["score"] is not None else None,
                            metadata={k: v for k, v in item.items() if k not in {"id", "memory", "score"}},
                        )
                    )
            return hits[: max(0, int(limit))]
        except Exception:
            logger.exception("mem0 search failed")
            return []

