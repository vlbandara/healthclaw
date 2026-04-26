from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session
from nanobot.store.base import MemoryRepository, SessionRepository


@dataclass(slots=True)
class RepoMaintenanceDeps:
    provider: LLMProvider
    model: str
    session_repo: SessionRepository
    memory_repo: MemoryRepository


class RepoConsolidator:
    """Repository-backed consolidation (platform mode).

    This is intentionally lightweight: in platform mode, the worker pool can run
    consolidation as a background job using repositories rather than workspace files.
    """

    def __init__(self, deps: RepoMaintenanceDeps):
        self._deps = deps

    async def maybe_consolidate(self, *, tenant_id: str, session: Session) -> None:
        # Placeholder: we keep current file-based Consolidator as the reference.
        # Platform consolidation will evolve into an eval-driven summarizer pipeline.
        if session.last_consolidated >= len(session.messages):
            return
        # Minimal safe behavior: do nothing unless a future phase enables it.
        return


class RepoDream:
    """Repository-backed Dream (platform mode).

    The existing Dream mutates workspace markdown and commits via GitStore.
    Platform Dream will instead update memory documents and semantic memory entries.
    """

    def __init__(self, deps: RepoMaintenanceDeps, timezone: str = "UTC"):
        self._deps = deps
        self._tz = timezone

    async def run(self, *, tenant_id: str) -> None:
        logger.info("RepoDream: not yet implemented for tenant {}", tenant_id)
        return

