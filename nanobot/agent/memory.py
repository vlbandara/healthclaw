"""Memory system: pure file I/O store, lightweight Consolidator, and Dream processor."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import weakref
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from zoneinfo import ZoneInfo

from loguru import logger

from nanobot.agent.runner import AgentRunner, AgentRunSpec
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.health.storage import is_health_workspace
from nanobot.utils.gitstore import GitStore
from nanobot.utils.helpers import (
    ensure_dir,
    estimate_message_tokens,
    estimate_prompt_tokens_chain,
    strip_think,
)
from nanobot.utils.prompt_templates import render_template

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider
    from nanobot.session.manager import Session, SessionManager


_INTEREST_SECTIONS = (
    "stable_interests",
    "active_curiosities",
    "avoid_topics",
)
_INTEREST_SECTION_TITLES = {
    "stable_interests": "Stable Interests",
    "active_curiosities": "Active Curiosities",
    "avoid_topics": "Avoid Topics",
}
_INTEREST_CAPTURE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("stable_interests", r"\b(?:i|we)\s+(?:really\s+)?(?:like|love|enjoy)\s+([^.!?\n]+)"),
    ("stable_interests", r"\b(?:i(?:'m| am)?|im)\s+(?:really\s+)?into\s+([^.!?\n]+)"),
    ("stable_interests", r"\b(?:my favorite(?: thing)? is|i(?:'m| am)? a fan of|im a fan of)\s+([^.!?\n]+)"),
    ("active_curiosities", r"\b(?:i(?:'m| am)?|im)\s+(?:curious about|interested in)\s+([^.!?\n]+)"),
    ("active_curiosities", r"\b(?:i want to learn|i(?:'m| am)? learning|im learning|i(?:'ve| have) been exploring)\s+([^.!?\n]+)"),
    ("active_curiosities", r"\b(?:let'?s|lets|we can)\s+talk about\s+([^.!?\n]+)"),
    ("avoid_topics", r"\b(?:don'?t|do not)\s+(?:talk to me about|ask me about|bring up|want to talk about|want to hear about)\s+([^.!?\n]+)"),
    ("avoid_topics", r"\b(?:i(?:'m| am)?|im)\s+not\s+(?:into|interested in)\s+([^.!?\n]+)"),
)
_INTEREST_SPLIT_RE = re.compile(r"\s*(?:,|/|;|\band\b|\bor\b)\s*", re.IGNORECASE)
_INTEREST_TRAILING_RE = re.compile(
    r"\s+(?:because|but|though|although|unless|since|when|while|if)\b.*$",
    re.IGNORECASE,
)


def _safe_timezone(value: str | None) -> ZoneInfo:
    try:
        return ZoneInfo((value or "").strip() or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _local_now(*, timezone: str | None, now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(_safe_timezone(timezone))


def _normalize_interest_topic(value: str) -> str:
    topic = str(value or "").strip().strip("\"'`")
    topic = re.sub(
        r"^(?:i(?:'m| am)?|im|we)\s+(?:really\s+)?(?:like|love|enjoy|am into|into|interested in|curious about|want to learn|have been exploring)\s+",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = _INTEREST_TRAILING_RE.sub("", topic).strip()
    topic = re.sub(r"^(?:the|a|an)\s+", "", topic, flags=re.IGNORECASE)
    topic = re.sub(r"\s+", " ", topic)
    topic = topic.rstrip(" .!?")
    return topic


def _split_interest_topics(raw: str) -> list[str]:
    parts = []
    for piece in _INTEREST_SPLIT_RE.split(raw):
        topic = _normalize_interest_topic(piece)
        if topic:
            parts.append(topic)
    return parts


def _extract_interest_signals(text: str) -> dict[str, list[str]]:
    lowered = str(text or "").strip()
    found = {section: [] for section in _INTEREST_SECTIONS}
    if not lowered:
        return found
    for section, pattern in _INTEREST_CAPTURE_PATTERNS:
        for match in re.finditer(pattern, lowered, flags=re.IGNORECASE):
            for topic in _split_interest_topics(match.group(1)):
                if len(topic) < 3:
                    continue
                found[section].append(topic)
    return found


def _interest_display(topic: str) -> str:
    cleaned = _normalize_interest_topic(topic)
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:]


# ---------------------------------------------------------------------------
# MemoryStore — pure file I/O layer
# ---------------------------------------------------------------------------

class MemoryStore:
    """Pure file I/O for memory files: MEMORY.md, history.jsonl, SOUL.md, USER.md."""

    _DEFAULT_MAX_HISTORY = 1000
    _LEGACY_ENTRY_START_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}[^\]]*)\]\s*")
    _LEGACY_TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\s*")
    _LEGACY_RAW_MESSAGE_RE = re.compile(
        r"^\[\d{4}-\d{2}-\d{2}[^\]]*\]\s+[A-Z][A-Z0-9_]*(?:\s+\[tools:\s*[^\]]+\])?:"
    )

    def __init__(self, workspace: Path, max_history_entries: int = _DEFAULT_MAX_HISTORY):
        self.workspace = workspace
        self.max_history_entries = max_history_entries
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.interest_file = self.memory_dir / "INTERESTS.md"
        self.history_file = self.memory_dir / "history.jsonl"
        self.legacy_history_file = self.memory_dir / "HISTORY.md"
        self.soul_file = workspace / "SOUL.md"
        self.user_file = workspace / "USER.md"
        self._cursor_file = self.memory_dir / ".cursor"
        self._dream_cursor_file = self.memory_dir / ".dream_cursor"
        self._engagement_state_file = self.memory_dir / ".engagement_state.json"
        self._git = GitStore(workspace, tracked_files=[
            "SOUL.md", "USER.md", "memory/MEMORY.md", "memory/INTERESTS.md",
        ])
        self._archive_legacy_autonomy_state()
        self._maybe_migrate_legacy_history()

    @property
    def git(self) -> GitStore:
        return self._git

    # -- generic helpers -----------------------------------------------------

    @staticmethod
    def read_file(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _archive_legacy_autonomy_state(self) -> None:
        legacy_dir = self.workspace / "autonomy"
        if not legacy_dir.exists():
            return
        archive_root = ensure_dir(self.memory_dir / "legacy_autonomy")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = archive_root / f"autonomy-{stamp}"
        suffix = 2
        while target.exists():
            target = archive_root / f"autonomy-{stamp}-{suffix}"
            suffix += 1
        try:
            shutil.move(str(legacy_dir), str(target))
            logger.info("Archived legacy autonomy state to {}", target)
        except Exception:
            logger.exception("Failed to archive legacy autonomy state at {}", legacy_dir)

    def _maybe_migrate_legacy_history(self) -> None:
        """One-time upgrade from legacy HISTORY.md to history.jsonl.

        The migration is best-effort and prioritizes preserving as much content
        as possible over perfect parsing.
        """
        if not self.legacy_history_file.exists():
            return
        if self.history_file.exists() and self.history_file.stat().st_size > 0:
            return

        try:
            legacy_text = self.legacy_history_file.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            logger.exception("Failed to read legacy HISTORY.md for migration")
            return

        entries = self._parse_legacy_history(legacy_text)
        try:
            if entries:
                self._write_entries(entries)
                last_cursor = entries[-1]["cursor"]
                self._cursor_file.write_text(str(last_cursor), encoding="utf-8")
                # Default to "already processed" so upgrades do not replay the
                # user's entire historical archive into Dream on first start.
                self._dream_cursor_file.write_text(str(last_cursor), encoding="utf-8")

            backup_path = self._next_legacy_backup_path()
            self.legacy_history_file.replace(backup_path)
            logger.info(
                "Migrated legacy HISTORY.md to history.jsonl ({} entries)",
                len(entries),
            )
        except Exception:
            logger.exception("Failed to migrate legacy HISTORY.md")

    def _parse_legacy_history(self, text: str) -> list[dict[str, Any]]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            return []

        fallback_timestamp = self._legacy_fallback_timestamp()
        entries: list[dict[str, Any]] = []
        chunks = self._split_legacy_history_chunks(normalized)

        for cursor, chunk in enumerate(chunks, start=1):
            timestamp = fallback_timestamp
            content = chunk
            match = self._LEGACY_TIMESTAMP_RE.match(chunk)
            if match:
                timestamp = match.group(1)
                remainder = chunk[match.end():].lstrip()
                if remainder:
                    content = remainder

            entries.append({
                "cursor": cursor,
                "timestamp": timestamp,
                "content": content,
            })
        return entries

    def _split_legacy_history_chunks(self, text: str) -> list[str]:
        lines = text.split("\n")
        chunks: list[str] = []
        current: list[str] = []
        saw_blank_separator = False

        for line in lines:
            if saw_blank_separator and line.strip() and current:
                chunks.append("\n".join(current).strip())
                current = [line]
                saw_blank_separator = False
                continue
            if self._should_start_new_legacy_chunk(line, current):
                chunks.append("\n".join(current).strip())
                current = [line]
                saw_blank_separator = False
                continue
            current.append(line)
            saw_blank_separator = not line.strip()

        if current:
            chunks.append("\n".join(current).strip())
        return [chunk for chunk in chunks if chunk]

    def _should_start_new_legacy_chunk(self, line: str, current: list[str]) -> bool:
        if not current:
            return False
        if not self._LEGACY_ENTRY_START_RE.match(line):
            return False
        if self._is_raw_legacy_chunk(current) and self._LEGACY_RAW_MESSAGE_RE.match(line):
            return False
        return True

    def _is_raw_legacy_chunk(self, lines: list[str]) -> bool:
        first_nonempty = next((line for line in lines if line.strip()), "")
        match = self._LEGACY_TIMESTAMP_RE.match(first_nonempty)
        if not match:
            return False
        return first_nonempty[match.end():].lstrip().startswith("[RAW]")

    def _legacy_fallback_timestamp(self) -> str:
        try:
            return datetime.fromtimestamp(
                self.legacy_history_file.stat().st_mtime,
            ).strftime("%Y-%m-%d %H:%M")
        except OSError:
            return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _next_legacy_backup_path(self) -> Path:
        candidate = self.memory_dir / "HISTORY.md.bak"
        suffix = 2
        while candidate.exists():
            candidate = self.memory_dir / f"HISTORY.md.bak.{suffix}"
            suffix += 1
        return candidate

    # -- MEMORY.md (long-term facts) -----------------------------------------

    def read_memory(self) -> str:
        return self.read_file(self.memory_file)

    def write_memory(self, content: str) -> None:
        self.memory_file.write_text(content, encoding="utf-8")

    # -- SOUL.md -------------------------------------------------------------

    def read_soul(self) -> str:
        return self.read_file(self.soul_file)

    def write_soul(self, content: str) -> None:
        self.soul_file.write_text(content, encoding="utf-8")

    # -- USER.md -------------------------------------------------------------

    def read_user(self) -> str:
        return self.read_file(self.user_file)

    def write_user(self, content: str) -> None:
        self.user_file.write_text(content, encoding="utf-8")

    # -- INTERESTS.md --------------------------------------------------------

    def read_interest_memory(self) -> str:
        return self.read_file(self.interest_file)

    def write_interest_memory(self, content: str) -> None:
        self.interest_file.write_text(content.rstrip() + "\n", encoding="utf-8")

    # -- engagement state ----------------------------------------------------

    def _default_engagement_state(self) -> dict[str, Any]:
        return {
            "stable_interests": [],
            "active_curiosities": [],
            "avoid_topics": [],
            "reconnect_topics": [],
            "last_user_message_at": "",
            "last_user_local_date": "",
            "last_interest_digest_local_date": "",
            "delivery": {
                "last_sent_at": "",
                "last_sent_local_date": "",
                "recent_topics": [],
            },
        }

    def read_engagement_state(self) -> dict[str, Any]:
        if not self._engagement_state_file.exists():
            return self._default_engagement_state()
        try:
            data = json.loads(self._engagement_state_file.read_text(encoding="utf-8"))
        except Exception:
            return self._default_engagement_state()
        if not isinstance(data, dict):
            return self._default_engagement_state()
        state = self._default_engagement_state()
        state.update(data)
        delivery = state.get("delivery")
        if not isinstance(delivery, dict):
            delivery = {}
        merged_delivery = dict(self._default_engagement_state()["delivery"])
        merged_delivery.update(delivery)
        state["delivery"] = merged_delivery
        return state

    def write_engagement_state(self, state: dict[str, Any]) -> None:
        payload = self._default_engagement_state()
        payload.update(state or {})
        delivery = dict(self._default_engagement_state()["delivery"])
        delivery.update(payload.get("delivery") or {})
        payload["delivery"] = delivery
        self._engagement_state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _interest_section_items(self, state: dict[str, Any], key: str) -> list[dict[str, Any]]:
        values = state.get(key) or []
        return [item for item in values if isinstance(item, dict) and _normalize_interest_topic(item.get("topic", ""))]

    def _upsert_interest_item(
        self,
        items: list[dict[str, Any]],
        *,
        topic: str,
        evidence: str,
        seen_at: str,
    ) -> None:
        normalized = _normalize_interest_topic(topic).lower()
        if not normalized:
            return
        for item in items:
            if _normalize_interest_topic(item.get("topic", "")).lower() != normalized:
                continue
            item["last_seen_at"] = seen_at
            item["mentions"] = int(item.get("mentions") or 0) + 1
            item["topic"] = _interest_display(topic)
            evidence_lines = [str(line).strip() for line in (item.get("evidence") or []) if str(line).strip()]
            if evidence and evidence not in evidence_lines:
                evidence_lines.append(evidence)
            item["evidence"] = evidence_lines[-3:]
            return
        items.append(
            {
                "topic": _interest_display(topic),
                "first_seen_at": seen_at,
                "last_seen_at": seen_at,
                "mentions": 1,
                "evidence": [evidence] if evidence else [],
            }
        )

    def _recompute_reconnect_topics(self, state: dict[str, Any]) -> None:
        avoids = {
            _normalize_interest_topic(item.get("topic", "")).lower()
            for item in self._interest_section_items(state, "avoid_topics")
        }
        topics: list[str] = []
        for key in ("stable_interests", "active_curiosities"):
            for item in self._interest_section_items(state, key):
                topic = _interest_display(str(item.get("topic") or ""))
                if not topic:
                    continue
                if topic.lower() in avoids:
                    continue
                if topic not in topics:
                    topics.append(topic)
        state["reconnect_topics"] = topics[:8]

    def _render_interest_memory(self, state: dict[str, Any]) -> str:
        lines = ["# Interest Memory", "", "Hidden internal summary of what keeps the user engaged."]
        for key in ("stable_interests", "active_curiosities", "avoid_topics"):
            lines.extend(["", f"## {_INTEREST_SECTION_TITLES[key]}"])
            items = self._interest_section_items(state, key)
            if not items:
                lines.append("- None recorded yet.")
                continue
            for item in items:
                topic = _interest_display(str(item.get("topic") or ""))
                evidence = [str(line).strip() for line in (item.get("evidence") or []) if str(line).strip()]
                if evidence:
                    lines.append(f"- {topic}: {evidence[-1]}")
                else:
                    lines.append(f"- {topic}")
        lines.extend(["", "## Reconnect Topics"])
        reconnect_topics = [topic for topic in (state.get("reconnect_topics") or []) if _normalize_interest_topic(topic)]
        if reconnect_topics:
            for topic in reconnect_topics:
                lines.append(f"- {_interest_display(str(topic))}")
        else:
            lines.append("- None recorded yet.")
        return "\n".join(lines).rstrip() + "\n"

    def _persist_interest_state(self, state: dict[str, Any]) -> None:
        self._recompute_reconnect_topics(state)
        self.write_engagement_state(state)
        self.write_interest_memory(self._render_interest_memory(state))

    def record_user_activity(self, *, timezone: str | None, now: datetime | None = None) -> None:
        local_now = _local_now(timezone=timezone, now=now)
        state = self.read_engagement_state()
        state["last_user_message_at"] = local_now.replace(microsecond=0).isoformat()
        state["last_user_local_date"] = local_now.strftime("%Y-%m-%d")
        self.write_engagement_state(state)

    def capture_interest_signals(
        self,
        text: str,
        *,
        timezone: str | None,
        now: datetime | None = None,
    ) -> bool:
        signals = _extract_interest_signals(text)
        if not any(signals.values()):
            return False
        local_now = _local_now(timezone=timezone, now=now)
        seen_at = local_now.replace(microsecond=0).isoformat()
        evidence = str(text or "").strip()
        state = self.read_engagement_state()
        for section in _INTEREST_SECTIONS:
            items = self._interest_section_items(state, section)
            for topic in signals[section]:
                self._upsert_interest_item(
                    items,
                    topic=topic,
                    evidence=evidence,
                    seen_at=seen_at,
                )
            state[section] = items
        self._persist_interest_state(state)
        return True

    def apply_interest_digest(self, content: str, *, local_date: str) -> None:
        markdown = str(content or "").strip()
        if not markdown:
            self.mark_interest_digest(local_date=local_date)
            return
        self.write_interest_memory(markdown)
        state = self.read_engagement_state()
        current_section = ""
        parsed: dict[str, list[str]] = {key: [] for key in _INTEREST_SECTIONS}
        reconnect_topics: list[str] = []
        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if line.startswith("## "):
                title = line[3:].strip().lower()
                if title == "stable interests":
                    current_section = "stable_interests"
                elif title == "active curiosities":
                    current_section = "active_curiosities"
                elif title == "avoid topics":
                    current_section = "avoid_topics"
                elif title == "reconnect topics":
                    current_section = "reconnect_topics"
                else:
                    current_section = ""
                continue
            if not line.startswith("- "):
                continue
            topic = _normalize_interest_topic(line[2:].split(":", 1)[0])
            if not topic:
                continue
            if current_section == "reconnect_topics":
                reconnect_topics.append(_interest_display(topic))
            elif current_section in parsed:
                parsed[current_section].append(topic)
        local_timestamp = f"{local_date}T00:00:00"
        for section, topics in parsed.items():
            items = self._interest_section_items(state, section)
            for topic in topics:
                self._upsert_interest_item(items, topic=topic, evidence="", seen_at=local_timestamp)
            state[section] = items
        if reconnect_topics:
            state["reconnect_topics"] = reconnect_topics[:8]
        state["last_interest_digest_local_date"] = local_date
        self.write_engagement_state(state)

    def mark_interest_digest(self, *, local_date: str) -> None:
        state = self.read_engagement_state()
        state["last_interest_digest_local_date"] = local_date
        self.write_engagement_state(state)

    def record_engagement_delivery(
        self,
        *,
        topic: str,
        timezone: str | None,
        now: datetime | None = None,
    ) -> None:
        local_now = _local_now(timezone=timezone, now=now)
        state = self.read_engagement_state()
        delivery = dict(state.get("delivery") or {})
        delivery["last_sent_at"] = local_now.replace(microsecond=0).isoformat()
        delivery["last_sent_local_date"] = local_now.strftime("%Y-%m-%d")
        recent_topics = [str(item).strip() for item in (delivery.get("recent_topics") or []) if str(item).strip()]
        cleaned_topic = _interest_display(topic)
        if cleaned_topic:
            recent_topics.append(cleaned_topic)
        delivery["recent_topics"] = recent_topics[-8:]
        state["delivery"] = delivery
        self.write_engagement_state(state)

    # -- context injection (used by context.py) ------------------------------

    def get_memory_context(self) -> str:
        long_term = self.read_memory()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    def get_interest_context(self) -> str:
        interests = self.read_interest_memory()
        return f"## Interest Memory\n{interests}" if interests else ""

    # -- history.jsonl — append-only, JSONL format ---------------------------

    def append_history(self, entry: str) -> int:
        """Append *entry* to history.jsonl and return its auto-incrementing cursor."""
        cursor = self._next_cursor()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        record = {"cursor": cursor, "timestamp": ts, "content": strip_think(entry.rstrip()) or entry.rstrip()}
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._cursor_file.write_text(str(cursor), encoding="utf-8")
        return cursor

    def _next_cursor(self) -> int:
        """Read the current cursor counter and return next value."""
        if self._cursor_file.exists():
            try:
                return int(self._cursor_file.read_text(encoding="utf-8").strip()) + 1
            except (ValueError, OSError):
                pass
        # Fallback: read last line's cursor from the JSONL file.
        last = self._read_last_entry()
        if last:
            return last["cursor"] + 1
        return 1

    def read_unprocessed_history(self, since_cursor: int) -> list[dict[str, Any]]:
        """Return history entries with cursor > *since_cursor*."""
        return [e for e in self._read_entries() if e["cursor"] > since_cursor]

    def read_recent_history(self, limit: int = 40) -> list[dict[str, Any]]:
        entries = self._read_entries()
        if limit <= 0:
            return entries
        return entries[-limit:]

    def compact_history(self) -> None:
        """Drop oldest entries if the file exceeds *max_history_entries*."""
        if self.max_history_entries <= 0:
            return
        entries = self._read_entries()
        if len(entries) <= self.max_history_entries:
            return
        kept = entries[-self.max_history_entries:]
        self._write_entries(kept)

    # -- JSONL helpers -------------------------------------------------------

    def _read_entries(self) -> list[dict[str, Any]]:
        """Read all entries from history.jsonl."""
        entries: list[dict[str, Any]] = []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except FileNotFoundError:
            pass
        return entries

    def _read_last_entry(self) -> dict[str, Any] | None:
        """Read the last entry from the JSONL file efficiently."""
        try:
            with open(self.history_file, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return None
                read_size = min(size, 4096)
                f.seek(size - read_size)
                data = f.read().decode("utf-8")
                lines = [ln for ln in data.split("\n") if ln.strip()]
                if not lines:
                    return None
                return json.loads(lines[-1])
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _write_entries(self, entries: list[dict[str, Any]]) -> None:
        """Overwrite history.jsonl with the given entries."""
        with open(self.history_file, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -- dream cursor --------------------------------------------------------

    def get_last_dream_cursor(self) -> int:
        if self._dream_cursor_file.exists():
            try:
                return int(self._dream_cursor_file.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                pass
        return 0

    def set_last_dream_cursor(self, cursor: int) -> None:
        self._dream_cursor_file.write_text(str(cursor), encoding="utf-8")

    @property
    def dream_pending_file(self) -> Path:
        return self.memory_dir / ".dream_pending.json"

    def read_dream_pending(self) -> dict[str, Any] | None:
        path = self.dream_pending_file
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def write_dream_pending(self, analysis: str, end_cursor: int) -> None:
        payload = {"analysis": analysis, "end_cursor": end_cursor}
        self.dream_pending_file.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def clear_dream_pending(self) -> None:
        try:
            self.dream_pending_file.unlink(missing_ok=True)
        except OSError:
            pass

    # -- message formatting utility ------------------------------------------

    @staticmethod
    def _format_messages(messages: list[dict]) -> str:
        lines = []
        for message in messages:
            if not message.get("content"):
                continue
            tools = f" [tools: {', '.join(message['tools_used'])}]" if message.get("tools_used") else ""
            lines.append(
                f"[{message.get('timestamp', '?')[:16]}] {message['role'].upper()}{tools}: {message['content']}"
            )
        return "\n".join(lines)

    def raw_archive(self, messages: list[dict]) -> None:
        """Fallback: dump raw messages to history.jsonl without LLM summarization."""
        self.append_history(
            f"[RAW] {len(messages)} messages\n"
            f"{self._format_messages(messages)}"
        )
        logger.warning(
            "Memory consolidation degraded: raw-archived {} messages", len(messages)
        )



# ---------------------------------------------------------------------------
# Consolidator — lightweight token-budget triggered consolidation
# ---------------------------------------------------------------------------


class Consolidator:
    """Lightweight consolidation: summarizes evicted messages into history.jsonl."""

    _MAX_CONSOLIDATION_ROUNDS = 5

    _SAFETY_BUFFER = 1024  # extra headroom for tokenizer estimation drift

    def __init__(
        self,
        store: MemoryStore,
        provider: LLMProvider,
        model: str,
        sessions: SessionManager,
        context_window_tokens: int,
        build_messages: Callable[..., list[dict[str, Any]]],
        get_tool_definitions: Callable[[], list[dict[str, Any]]],
        max_completion_tokens: int = 4096,
    ):
        self.store = store
        self.provider = provider
        self.model = model
        self.sessions = sessions
        self.context_window_tokens = context_window_tokens
        self.max_completion_tokens = max_completion_tokens
        self._build_messages = build_messages
        self._get_tool_definitions = get_tool_definitions
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )

    def get_lock(self, session_key: str) -> asyncio.Lock:
        """Return the shared consolidation lock for one session."""
        return self._locks.setdefault(session_key, asyncio.Lock())

    def pick_consolidation_boundary(
        self,
        session: Session,
        tokens_to_remove: int,
    ) -> tuple[int, int] | None:
        """Pick a user-turn boundary that removes enough old prompt tokens."""
        start = session.last_consolidated
        if start >= len(session.messages) or tokens_to_remove <= 0:
            return None

        removed_tokens = 0
        last_boundary: tuple[int, int] | None = None
        for idx in range(start, len(session.messages)):
            message = session.messages[idx]
            if idx > start and message.get("role") == "user":
                last_boundary = (idx, removed_tokens)
                if removed_tokens >= tokens_to_remove:
                    return last_boundary
            removed_tokens += estimate_message_tokens(message)

        return last_boundary

    def estimate_session_prompt_tokens(self, session: Session) -> tuple[int, str]:
        """Estimate current prompt size for the normal session history view."""
        history = session.get_history(max_messages=0)
        channel, chat_id = (session.key.split(":", 1) if ":" in session.key else (None, None))
        probe_messages = self._build_messages(
            history=history,
            current_message="[token-probe]",
            channel=channel,
            chat_id=chat_id,
        )
        return estimate_prompt_tokens_chain(
            self.provider,
            self.model,
            probe_messages,
            self._get_tool_definitions(),
        )

    async def archive(self, messages: list[dict]) -> bool:
        """Summarize messages via LLM and append to history.jsonl.

        Returns True on success (or degraded success), False if nothing to do.
        """
        if not messages:
            return False
        try:
            formatted = MemoryStore._format_messages(messages)
            response = await self.provider.chat_with_retry(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": render_template(
                            "agent/consolidator_archive.md",
                            strip=True,
                        ),
                    },
                    {"role": "user", "content": formatted},
                ],
                tools=None,
                tool_choice=None,
            )
            summary = response.content or "[no summary]"
            self.store.append_history(summary)
            return True
        except Exception:
            logger.warning("Consolidation LLM call failed, raw-dumping to history")
            self.store.raw_archive(messages)
            return True

    async def maybe_consolidate_by_tokens(self, session: Session) -> None:
        """Loop: archive old messages until prompt fits within safe budget.

        The budget reserves space for completion tokens and a safety buffer
        so the LLM request never exceeds the context window.
        """
        if not session.messages or self.context_window_tokens <= 0:
            return

        lock = self.get_lock(session.key)
        async with lock:
            budget = self.context_window_tokens - self.max_completion_tokens - self._SAFETY_BUFFER
            target = budget // 2
            estimated, source = self.estimate_session_prompt_tokens(session)
            if estimated <= 0:
                return
            if estimated < budget:
                logger.debug(
                    "Token consolidation idle {}: {}/{} via {}",
                    session.key,
                    estimated,
                    self.context_window_tokens,
                    source,
                )
                return

            for round_num in range(self._MAX_CONSOLIDATION_ROUNDS):
                if estimated <= target:
                    return

                boundary = self.pick_consolidation_boundary(session, max(1, estimated - target))
                if boundary is None:
                    logger.debug(
                        "Token consolidation: no safe boundary for {} (round {})",
                        session.key,
                        round_num,
                    )
                    return

                end_idx = boundary[0]
                chunk = session.messages[session.last_consolidated:end_idx]
                if not chunk:
                    return

                logger.info(
                    "Token consolidation round {} for {}: {}/{} via {}, chunk={} msgs",
                    round_num,
                    session.key,
                    estimated,
                    self.context_window_tokens,
                    source,
                    len(chunk),
                )
                if not await self.archive(chunk):
                    return
                session.last_consolidated = end_idx
                self.sessions.save(session)

                estimated, source = self.estimate_session_prompt_tokens(session)
                if estimated <= 0:
                    return


# ---------------------------------------------------------------------------
# Dream — heavyweight cron-scheduled memory consolidation
# ---------------------------------------------------------------------------


class Dream:
    """Two-phase memory processor: analyze history.jsonl, then edit files via AgentRunner.

    Phase 1 produces an analysis summary (plain LLM call).
    Phase 2 delegates to AgentRunner with read_file / edit_file tools so the
    LLM can make targeted, incremental edits instead of replacing entire files.
    """

    def __init__(
        self,
        store: MemoryStore,
        provider: LLMProvider,
        model: str,
        max_batch_size: int = 20,
        max_iterations: int = 10,
        max_tool_result_chars: int = 16_000,
        timezone: str | None = None,
        interest_quiet_hours: tuple[str, str] = ("23:00", "06:00"),
    ):
        self.store = store
        self.provider = provider
        self.model = model
        self.max_batch_size = max_batch_size
        self.max_iterations = max_iterations
        self.max_tool_result_chars = max_tool_result_chars
        self.timezone = timezone or "UTC"
        self.interest_quiet_hours = interest_quiet_hours
        self._runner = AgentRunner(provider)
        self._tools = self._build_tools()

    # -- tool registry -------------------------------------------------------

    def _build_tools(self) -> ToolRegistry:
        """Build a minimal tool registry for the Dream agent."""
        from nanobot.agent.tools.filesystem import EditFileTool, ReadFileTool

        tools = ToolRegistry()
        workspace = self.store.workspace
        tools.register(ReadFileTool(workspace=workspace, allowed_dir=workspace))
        tools.register(EditFileTool(workspace=workspace, allowed_dir=workspace))
        return tools

    def _render_dream_system_prompt(self, template_name: str) -> str:
        prompt = render_template(template_name, strip=True)
        if is_health_workspace(self.store.workspace):
            prompt += "\n\n" + render_template("health/dream_appendix.md", strip=True)
        return prompt

    @staticmethod
    def _parse_clock(value: str) -> tuple[int, int]:
        try:
            hour_str, minute_str = value.split(":", 1)
            return int(hour_str), int(minute_str)
        except Exception:
            return 23, 0

    def _interest_timezone(self) -> str:
        if is_health_workspace(self.store.workspace):
            try:
                profile = json.loads((self.store.workspace / "health" / "profile.json").read_text(encoding="utf-8"))
            except Exception:
                profile = {}
            timezone = str(profile.get("timezone") or "").strip()
            if timezone:
                return timezone
        return self.timezone

    def _interest_local_now(self, now: datetime | None = None) -> datetime:
        return _local_now(timezone=self._interest_timezone(), now=now)

    def _interest_digest_due(self, *, now: datetime | None = None) -> tuple[bool, str]:
        local_now = self._interest_local_now(now)
        local_date = local_now.strftime("%Y-%m-%d")
        state = self.store.read_engagement_state()
        if str(state.get("last_interest_digest_local_date") or "").strip() == local_date:
            return False, local_date

        start, end = self.interest_quiet_hours
        if is_health_workspace(self.store.workspace):
            try:
                profile = json.loads((self.store.workspace / "health" / "profile.json").read_text(encoding="utf-8"))
            except Exception:
                profile = {}
            sleep_time = str(((profile.get("routines") or {}).get("sleep_time")) or "").strip()
            if sleep_time:
                start = sleep_time

        start_h, start_m = self._parse_clock(start)
        end_h, end_m = self._parse_clock(end)
        current_minutes = local_now.hour * 60 + local_now.minute
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        if start_minutes == end_minutes:
            quiet = False
        elif start_minutes < end_minutes:
            quiet = start_minutes <= current_minutes < end_minutes
        else:
            quiet = current_minutes >= start_minutes or current_minutes < end_minutes
        return quiet, local_date

    async def _maybe_run_interest_digest(self) -> bool:
        due, local_date = self._interest_digest_due()
        if not due:
            return False

        recent_history = self.store.read_recent_history(limit=30)
        interest_memory = self.store.read_interest_memory().strip() or "(empty)"
        user_md = self.store.read_user().strip() or "(empty)"
        memory_md = self.store.read_memory().strip() or "(empty)"
        if not recent_history and interest_memory == "(empty)":
            self.store.mark_interest_digest(local_date=local_date)
            return False

        history_text = "\n".join(
            f"[{entry['timestamp']}] {entry['content']}"
            for entry in recent_history
        ) or "(empty)"
        prompt = (
            f"## Current INTERESTS.md\n{interest_memory}\n\n"
            f"## Current USER.md\n{user_md}\n\n"
            f"## Current MEMORY.md\n{memory_md}\n\n"
            f"## Recent History\n{history_text}"
        )
        try:
            response = await self.provider.chat_with_retry(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": render_template("agent/interest_digest.md", strip=True),
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                tool_choice=None,
            )
        except Exception:
            logger.exception("Interest digest failed")
            return False

        content = str(response.content or "").strip()
        self.store.apply_interest_digest(content, local_date=local_date)
        logger.info("Interest digest updated for {}", local_date)
        return True

    # -- main entry ----------------------------------------------------------

    def _file_context_block(self) -> str:
        current_memory = self.store.read_memory() or "(empty)"
        current_soul = self.store.read_soul() or "(empty)"
        current_user = self.store.read_user() or "(empty)"
        return (
            f"## Current MEMORY.md\n{current_memory}\n\n"
            f"## Current SOUL.md\n{current_soul}\n\n"
            f"## Current USER.md\n{current_user}"
        )

    async def _run_phase2(self, analysis: str, file_context: str):
        phase2_prompt = f"## Analysis Result\n{analysis}\n\n{file_context}"
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": self._render_dream_system_prompt("agent/dream_phase2.md"),
            },
            {"role": "user", "content": phase2_prompt},
        ]
        return await self._runner.run(AgentRunSpec(
            initial_messages=messages,
            tools=self._tools,
            model=self.model,
            max_iterations=self.max_iterations,
            max_tool_result_chars=self.max_tool_result_chars,
            fail_on_tool_error=False,
        ))

    async def run(self) -> bool:
        """Process unprocessed history entries. Returns True if work was done."""
        file_context = self._file_context_block()
        pending = self.store.read_dream_pending()
        if pending:
            analysis = str(pending.get("analysis") or "")
            try:
                end_cursor = int(pending["end_cursor"])
            except (KeyError, TypeError, ValueError):
                self.store.clear_dream_pending()
                return False
            if not analysis:
                self.store.clear_dream_pending()
                return False
            logger.info("Dream: retry Phase 2 for pending batch (cursor target {})", end_cursor)
            try:
                result = await self._run_phase2(analysis, file_context)
            except Exception:
                logger.exception("Dream Phase 2 failed (retry)")
                return True
            if not result or result.stop_reason != "completed":
                logger.warning("Dream Phase 2 retry incomplete ({})", getattr(result, "stop_reason", None))
                return True
            finalized = self._dream_success_finalize(result, end_cursor=end_cursor, batch_timestamp="")
            digested = await self._maybe_run_interest_digest()
            return finalized or digested

        last_cursor = self.store.get_last_dream_cursor()
        entries = self.store.read_unprocessed_history(since_cursor=last_cursor)
        if not entries:
            return await self._maybe_run_interest_digest()

        batch = entries[: self.max_batch_size]
        logger.info(
            "Dream: processing {} entries (cursor {}→{}), batch={}",
            len(entries), last_cursor, batch[-1]["cursor"], len(batch),
        )

        history_text = "\n".join(
            f"[{e['timestamp']}] {e['content']}" for e in batch
        )
        phase1_prompt = f"## Conversation History\n{history_text}\n\n{file_context}"

        try:
            phase1_response = await self.provider.chat_with_retry(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._render_dream_system_prompt("agent/dream_phase1.md"),
                    },
                    {"role": "user", "content": phase1_prompt},
                ],
                tools=None,
                tool_choice=None,
            )
            analysis = phase1_response.content or ""
            logger.debug("Dream Phase 1 complete ({} chars)", len(analysis))
        except Exception:
            logger.exception("Dream Phase 1 failed")
            return False

        end_cursor = batch[-1]["cursor"]
        batch_ts = batch[-1]["timestamp"]

        try:
            result = await self._run_phase2(analysis, file_context)
            logger.debug(
                "Dream Phase 2 complete: stop_reason={}, tool_events={}",
                result.stop_reason, len(result.tool_events),
            )
        except Exception:
            logger.exception("Dream Phase 2 failed")
            self.store.write_dream_pending(analysis, end_cursor)
            return True

        if result.stop_reason != "completed":
            self.store.write_dream_pending(analysis, end_cursor)
            logger.warning(
                "Dream incomplete ({}): saved pending for Phase 2 retry",
                result.stop_reason,
            )
            return True

        finalized = self._dream_success_finalize(result, end_cursor=end_cursor, batch_timestamp=batch_ts)
        digested = await self._maybe_run_interest_digest()
        return finalized or digested

    def _dream_success_finalize(self, result, *, end_cursor: int, batch_timestamp: str) -> bool:
        changelog: list[str] = []
        if result and result.tool_events:
            for event in result.tool_events:
                if event["status"] == "ok":
                    changelog.append(f"{event['name']}: {event['detail']}")

        self.store.set_last_dream_cursor(end_cursor)
        self.store.clear_dream_pending()
        self.store.compact_history()

        logger.info(
            "Dream done: {} change(s), cursor advanced to {}",
            len(changelog), end_cursor,
        )

        if changelog and self.store.git.is_initialized():
            ts = batch_timestamp or "unknown"
            sha = self.store.git.auto_commit(f"dream: {ts}, {len(changelog)} change(s)")
            if sha:
                logger.info("Dream commit: {}", sha)

        return True
