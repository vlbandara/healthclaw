"""Resolve on-disk nanobot workspace paths for health web chat."""

from __future__ import annotations

import os
import re
from pathlib import Path


def _safe_token_segment(token: str) -> str:
    return "".join(ch for ch in (token or "") if ch.isalnum() or ch in "-_").strip("-_")


def resolve_health_chat_workspace(*, token: str, workspace_root: Path) -> Path | None:
    """Return a workspace directory containing ``SOUL.md`` for this token, or None.

    Resolution order:

    1. Per-user bind mount (``NANOBOT_HEALTH_INSTANCE_WORKSPACE_ROOT/<token>``) — matches docker spawner ``user_id``.
    2. Single shared workspace when ``health/profile.json`` contains matching ``user_token``.
    """
    safe = _safe_token_segment(token)
    if not safe:
        return None

    bind_root = os.environ.get("NANOBOT_HEALTH_INSTANCE_WORKSPACE_ROOT", "").strip()
    if bind_root:
        candidate = Path(bind_root).expanduser().resolve() / safe
        if (candidate / "SOUL.md").is_file():
            return candidate

    gw = workspace_root.expanduser().resolve()
    if (gw / "SOUL.md").is_file():
        try:
            from nanobot.health.storage import HealthWorkspace

            prof = HealthWorkspace(gw).load_profile()
            if prof and str(prof.get("user_token") or "") == token:
                return gw
        except Exception:
            pass

    return None


def parse_lifecycle_stage(memory_md: Path) -> str:
    """Read ``memory/MEMORY.md`` and return lifecycle stage slug."""
    if not memory_md.is_file():
        return "early"
    try:
        text = memory_md.read_text(encoding="utf-8")
    except OSError:
        return "early"
    m = re.search(r"^-\s*Stage:\s*(\S+)", text, re.MULTILINE | re.IGNORECASE)
    if m:
        return m.group(1).strip().lower()
    return "early"


def rough_knowledge_score(memory_md: Path) -> int:
    """Heuristic 0–100: non-empty sections in MEMORY.md beyond baseline."""
    if not memory_md.is_file():
        return 0
    try:
        text = memory_md.read_text(encoding="utf-8")
    except OSError:
        return 0
    score = 15
    for heading in ("## Symptom Trends", "## Adherence Patterns", "## Goals And Supports", "## Lifecycle"):
        start = text.find(heading)
        if start == -1:
            continue
        chunk = text[start : start + 600]
        lines = [ln.strip() for ln in chunk.splitlines()[1:] if ln.strip() and not ln.startswith("#")]
        if any(not ln.startswith("- No ") and not ln.startswith("- Stage:") for ln in lines[:12]):
            score += 18
    return min(100, score)
