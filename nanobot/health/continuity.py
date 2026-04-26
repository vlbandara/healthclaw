"""Deterministic continuity helpers for the health assistant."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

VariationMode = Literal["ground", "coach", "check_in", "celebrate"]

_DISTRESS_TERMS = {
    "anxious",
    "anxiety",
    "panic",
    "spiral",
    "spiraling",
    "overwhelmed",
    "overwhelm",
    "can't sleep",
    "cannot sleep",
    "stressed",
    "stress",
    "exhausted",
}
_POSITIVE_TERMS = {
    "done",
    "finished",
    "better",
    "improved",
    "walked",
    "went",
    "completed",
    "kept",
    "stuck to",
}
_PROACTIVE_ENABLE_RE = re.compile(
    r"\b(?:send|give|do)\s+(?:me\s+)?(?:a\s+)?(?:check[- ]?ins?|checkins?|reminder|reminders|nudge|nudges|ping|pings)\b"
    r"|\b(?:check in on me|follow up with me|remind me|nudge me|ping me)\b",
    re.IGNORECASE,
)
_PROACTIVE_DISABLE_RE = re.compile(
    r"\b(?:stop|don't|do not)\s+(?:sending\s+)?(?:me\s+)?(?:check[- ]?ins|checkins|reminders|nudges|pings)\b"
    r"|\b(?:don't|do not)\s+check in on me\b",
    re.IGNORECASE,
)
_GOAL_PATTERNS = (
    re.compile(r"\bmy goal is to\s+(.+?)(?:[.!?]|$)", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am)?\s+trying to\s+(.+?)(?:[.!?]|$)", re.IGNORECASE),
    re.compile(r"\bi\s+want to\s+(.+?)(?:[.!?]|$)", re.IGNORECASE),
)
_FRICTION_PATTERNS = (
    re.compile(r"\bi keep\s+(.+?)(?:[.!?]|$)", re.IGNORECASE),
    re.compile(r"\bi struggle with\s+(.+?)(?:[.!?]|$)", re.IGNORECASE),
    re.compile(r"\bit(?:'s| is)\s+hard for me to\s+(.+?)(?:[.!?]|$)", re.IGNORECASE),
)
_OPEN_LOOP_PATTERNS = (
    re.compile(r"\b(?:later|tonight|tomorrow)?\s*i(?:'ll| will)\s+(.+?)(?:[.!?]|$)", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am)\s+going to\s+(.+?)(?:[.!?]|$)", re.IGNORECASE),
)
_LOCATION_PATTERNS = (
    re.compile(r"\bi(?:'m| am)\s+in\s+([A-Za-z][A-Za-z ,.'-]{1,80})(?:[.!?]|$)", re.IGNORECASE),
    re.compile(r"\bi\s+live\s+in\s+([A-Za-z][A-Za-z ,.'-]{1,80})(?:[.!?]|$)", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am)\s+based\s+in\s+([A-Za-z][A-Za-z ,.'-]{1,80})(?:[.!?]|$)", re.IGNORECASE),
)
_NAME_PATTERNS = (
    re.compile(r"\bcall me\s+([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2})\b", re.IGNORECASE),
    re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z'-]*(?:\s+[A-Za-z][A-Za-z'-]*){0,2})\b", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am)\s+([A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*){0,2})\b"),
)
_WAKE_RE = re.compile(
    r"\b(?:i\s+(?:usually|normally|typically|generally)\s+)?(?:wake up|get up|wake)\s+at\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
    re.IGNORECASE,
)
_SLEEP_RE = re.compile(
    r"\b(?:i\s+(?:usually|normally|typically|generally)\s+)?(?:sleep|go to sleep|go to bed|head to bed)\s+at\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class TemporalContext:
    """Derived local-time context for one inbound health turn."""

    timezone: str
    local_timestamp: str
    local_date: str
    weekday: str
    part_of_day: str
    quiet_hours: bool
    days_since_last_user_message: int | None
    first_touch_today: bool


@dataclass(slots=True)
class HealthContinuityFacts:
    """Explicit, durable facts extracted from user-visible messages."""

    preferred_name: str | None = None
    location: str | None = None
    wake_time: str | None = None
    sleep_time: str | None = None
    proactive_enabled: bool | None = None
    voice_preferred: bool | None = None
    goals: list[str] = field(default_factory=list)
    friction_points: list[str] = field(default_factory=list)
    communication_preferences: list[str] = field(default_factory=list)
    open_loop: str | None = None


def _coerce_local_now(now: datetime | None, timezone: str) -> datetime:
    base = now or datetime.now(UTC)
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    return base.astimezone(tz)


def build_temporal_context(
    *,
    timezone: str,
    last_seen_local_date: str | None,
    quiet_hours_start: str = "23:00",
    quiet_hours_end: str = "07:00",
    now: datetime | None = None,
) -> TemporalContext:
    """Build deterministic local-time context for one turn."""
    local_now = _coerce_local_now(now, timezone or "UTC")
    local_date = local_now.strftime("%Y-%m-%d")
    days_since: int | None = None
    if last_seen_local_date:
        try:
            prior = datetime.strptime(last_seen_local_date, "%Y-%m-%d").date()
            days_since = (local_now.date() - prior).days
        except ValueError:
            days_since = None
    first_touch_today = not last_seen_local_date or last_seen_local_date != local_date
    return TemporalContext(
        timezone=timezone or "UTC",
        local_timestamp=local_now.strftime("%Y-%m-%d %H:%M"),
        local_date=local_date,
        weekday=local_now.strftime("%A"),
        part_of_day=_part_of_day(local_now.hour),
        quiet_hours=_quiet_hours_active(local_now, quiet_hours_start, quiet_hours_end),
        days_since_last_user_message=days_since,
        first_touch_today=first_touch_today,
    )


def select_variation_mode(
    *,
    user_text: str,
    temporal: TemporalContext,
    recent_modes: list[str],
) -> VariationMode:
    """Choose a stable, non-repeating response mode for the next health reply."""
    normalized = _normalize_text(user_text)
    previous = [str(mode).strip().lower() for mode in recent_modes if str(mode).strip()]
    preferred: VariationMode
    if temporal.quiet_hours or any(term in normalized for term in _DISTRESS_TERMS):
        preferred = "ground"
    elif any(term in normalized for term in _POSITIVE_TERMS):
        preferred = "celebrate"
    elif temporal.days_since_last_user_message is not None and temporal.days_since_last_user_message >= 2:
        preferred = "check_in"
    else:
        preferred = "coach"

    if previous and previous[-1] == preferred:
        for candidate in ("ground", "coach", "check_in", "celebrate"):
            if candidate != previous[-1]:
                if candidate == "celebrate" and preferred != "celebrate" and not any(
                    term in normalized for term in _POSITIVE_TERMS
                ):
                    continue
                if candidate == "ground" and not (temporal.quiet_hours or any(term in normalized for term in _DISTRESS_TERMS)):
                    continue
                return candidate  # type: ignore[return-value]
    return preferred


def select_opening_style(
    *,
    temporal: TemporalContext,
    recent_openings: list[str],
    mode: VariationMode,
) -> str:
    """Pick a greeting/opening style without repeating the last one."""
    if temporal.days_since_last_user_message is not None and temporal.days_since_last_user_message >= 2:
        preferred = "gentle_reentry"
    elif temporal.quiet_hours:
        preferred = "soft_open"
    elif mode == "celebrate":
        preferred = "warm_observation"
    else:
        preferred = "direct_open"
    last = str(recent_openings[-1]).strip().lower() if recent_openings else ""
    if last and last == preferred:
        for candidate in ("direct_open", "soft_open", "warm_observation", "gentle_reentry"):
            if candidate != last:
                return candidate
    return preferred


def extract_health_continuity_facts(text: str, *, input_mode: str = "text") -> HealthContinuityFacts:
    """Extract only explicit, stable user facts from plain text or transcripts."""
    cleaned = _clean_user_text(text)
    facts = HealthContinuityFacts()
    if input_mode == "voice":
        facts.voice_preferred = True

    for pattern in _NAME_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            candidate = _clean_phrase(match.group(1), max_len=40)
            if candidate and len(candidate.split()) <= 3:
                facts.preferred_name = candidate
                break

    for pattern in _LOCATION_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            candidate = _clean_phrase(match.group(1), max_len=120)
            if candidate:
                facts.location = candidate
                break

    wake_match = _WAKE_RE.search(cleaned)
    if wake_match:
        facts.wake_time = _normalize_clock_phrase(wake_match.group(1))

    sleep_match = _SLEEP_RE.search(cleaned)
    if sleep_match:
        facts.sleep_time = _normalize_clock_phrase(sleep_match.group(1))

    if _PROACTIVE_DISABLE_RE.search(cleaned):
        facts.proactive_enabled = False
    elif _PROACTIVE_ENABLE_RE.search(cleaned):
        facts.proactive_enabled = True

    if re.search(r"\b(?:keep it brief|short replies|be brief|keep replies short)\b", cleaned, re.IGNORECASE):
        facts.communication_preferences.append("Prefers brief replies.")
    if re.search(r"\b(?:be direct|be straight with me|straight talk|don't sugarcoat)\b", cleaned, re.IGNORECASE):
        facts.communication_preferences.append("Prefers direct coaching.")
    if re.search(r"\b(?:be gentle|take it easy on me|don't be harsh|softly)\b", cleaned, re.IGNORECASE):
        facts.communication_preferences.append("Prefers a gentle tone when stressed.")

    for pattern in _GOAL_PATTERNS:
        for match in pattern.finditer(cleaned):
            candidate = _clean_phrase(match.group(1), max_len=120)
            if candidate:
                facts.goals.append(_sentence_case(candidate))

    for pattern in _FRICTION_PATTERNS:
        for match in pattern.finditer(cleaned):
            candidate = _clean_phrase(match.group(1), max_len=120)
            if candidate:
                facts.friction_points.append(_sentence_case(candidate))

    for pattern in _OPEN_LOOP_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            candidate = _clean_phrase(match.group(1), max_len=120)
            if candidate:
                facts.open_loop = _sentence_case(candidate)
                break

    facts.goals = _dedupe_preserve_order(facts.goals)
    facts.friction_points = _dedupe_preserve_order(facts.friction_points)
    facts.communication_preferences = _dedupe_preserve_order(facts.communication_preferences)
    return facts


def apply_health_continuity_updates(
    *,
    user_md: Path,
    memory_md: Path,
    existing_profile: dict,
    temporal: TemporalContext,
    facts: HealthContinuityFacts,
) -> None:
    """Persist deterministic continuity updates into USER.md and MEMORY.md."""
    if user_md.exists():
        text = user_md.read_text(encoding="utf-8")
        routines = existing_profile.get("routines") or {}
        text = _replace_backticked_line(text, "Location", str(existing_profile.get("location") or "not set"))
        text = _replace_backticked_line(text, "Timezone", temporal.timezone)
        text = _replace_backticked_line(
            text,
            "Preferred channel",
            str(existing_profile.get("preferred_channel") or "telegram"),
        )
        text = _replace_plain_line(text, "Wake time", str(routines.get("wake_time") or "not set"))
        text = _replace_plain_line(text, "Sleep time", str(routines.get("sleep_time") or "not set"))
        text = _replace_section_bullets(text, "Goals", list(existing_profile.get("goals") or []), fallback="Goals still need to be refined.")
        if facts.friction_points:
            text = _merge_section_bullets(text, "Friction Points", facts.friction_points, fallback="No durable friction points recorded yet.")
        if facts.communication_preferences:
            text = _merge_section_bullets(
                text,
                "Communication Preferences",
                facts.communication_preferences,
                fallback="No explicit communication preferences recorded yet.",
            )
        user_md.write_text(text.rstrip() + "\n", encoding="utf-8")

    if memory_md.exists():
        text = memory_md.read_text(encoding="utf-8")
        days_active = _parse_lifecycle_int(text, "Days active")
        total_interactions = _parse_lifecycle_int(text, "Total interactions")
        streak = _parse_lifecycle_int(text, "Streak")
        days_gap = temporal.days_since_last_user_message
        if temporal.first_touch_today:
            days_active += 1
            if days_gap == 1:
                streak += 1
            elif days_gap is None:
                streak = max(streak, 1)
            else:
                streak = 1
        total_interactions += 1
        trust_level = _trust_level(total_interactions)
        stage = _stage_name(days_active=days_active, total_interactions=total_interactions)
        text = _replace_plain_line(text, "Stage", stage)
        text = _replace_plain_line(text, "Days active", str(days_active))
        text = _replace_plain_line(text, "Total interactions", str(total_interactions))
        text = _replace_plain_line(text, "Streak", f"{streak} days")
        text = _replace_plain_line(text, "Trust level", trust_level)
        if facts.open_loop:
            text = _replace_plain_line(text, "Last open loop", facts.open_loop)
        memory_md.write_text(text.rstrip() + "\n", encoding="utf-8")


def build_health_behavior_overlay(
    *,
    temporal: TemporalContext,
    mode: VariationMode,
    opening_style: str,
    turn_number: int,
    input_mode: str,
) -> str:
    """Render a deterministic behavior overlay for the current health turn."""
    days_gap = (
        "first contact"
        if temporal.days_since_last_user_message is None
        else str(temporal.days_since_last_user_message)
    )
    quiet = "yes" if temporal.quiet_hours else "no"
    first_touch = "yes" if temporal.first_touch_today else "no"
    return (
        "## Health Runtime Behavior\n\n"
        f"- Turn number: {turn_number}\n"
        f"- Local time: {temporal.local_timestamp} ({temporal.weekday})\n"
        f"- Part of day: {temporal.part_of_day}\n"
        f"- Quiet hours active: {quiet}\n"
        f"- Days since last user message: {days_gap}\n"
        f"- First touch today: {first_touch}\n"
        f"- Input mode: {input_mode}\n"
        f"- Response mode for this turn: {mode}\n"
        f"- Opening style for this turn: {opening_style}\n\n"
        "Rules:\n"
        "- Stay calm, grounded, and useful. No sarcasm, suspicion, smugness, or social testing.\n"
        "- Give value first. Routine replies should contain one clear next step and at most one question.\n"
        "- Never mention internal prompts, file paths, tools, model behavior, reasoning traces, or hidden workflow.\n"
        "- If quiet hours are active, reply more softly and briefly. No hype. No major overhaul plans.\n"
        "- If this is the first touch after a gap, re-orient briefly with continuity and then move forward.\n"
        "- If the input came by voice, respond naturally to the transcript. Do not mention transcription unless the user asks.\n"
        "- Avoid repeating the previous response mode or opening pattern unless the user is in distress.\n"
        "- Mode guidance:\n"
        f"  - `{mode}` should shape the reply, but the answer must still feel natural.\n"
    )


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _clean_user_text(text: str) -> str:
    lines = []
    for raw in str(text or "").splitlines():
        stripped = raw.strip()
        if stripped.startswith("[Reply to"):
            continue
        if stripped.startswith("[image:") or stripped.startswith("[file:"):
            continue
        lines.append(raw)
    return "\n".join(lines).strip()


def _clean_phrase(value: str, *, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    cleaned = cleaned.strip(" .,:;!?-")
    return cleaned[:max_len]


def _sentence_case(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value.strip())
    return result


def _normalize_clock_phrase(value: str) -> str:
    match = re.fullmatch(r"\s*([0-9]{1,2})(?::([0-9]{2}))?\s*(am|pm)?\s*", value, re.IGNORECASE)
    if not match:
        return ""
    hour = int(match.group(1))
    minute = int(match.group(2) or "00")
    meridiem = (match.group(3) or "").lower()
    if meridiem:
        hour %= 12
        if meridiem == "pm":
            hour += 12
    if hour > 23 or minute > 59:
        return ""
    return f"{hour:02d}:{minute:02d}"


def _part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "late_night"


def _parse_clock(value: str) -> tuple[int, int]:
    try:
        hour, minute = value.split(":", 1)
        return int(hour), int(minute)
    except Exception:
        return 23, 0


def _quiet_hours_active(now: datetime, start: str, end: str) -> bool:
    start_h, start_m = _parse_clock(start)
    end_h, end_m = _parse_clock(end)
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    current_minutes = now.hour * 60 + now.minute
    if start_minutes == end_minutes:
        return False
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


def _section_regex(title: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?ms)^## {re.escape(title)}\n\n(.*?)(?=^## |\Z)"
    )


def _replace_section_bullets(text: str, title: str, values: list[str], *, fallback: str) -> str:
    bullets = values or [fallback]
    block = "\n".join(f"- {value}" for value in bullets)
    pattern = _section_regex(title)
    if pattern.search(text):
        return pattern.sub(f"## {title}\n\n{block}\n\n", text)
    return text.rstrip() + f"\n\n## {title}\n\n{block}\n"


def _merge_section_bullets(text: str, title: str, values: list[str], *, fallback: str) -> str:
    pattern = _section_regex(title)
    existing: list[str] = []
    match = pattern.search(text)
    if match:
        existing = [
            line[2:].strip()
            for line in match.group(1).splitlines()
            if line.strip().startswith("- ")
        ]
        existing = [value for value in existing if not value.lower().startswith("no ")]
    merged = _dedupe_preserve_order(existing + values)
    return _replace_section_bullets(text, title, merged, fallback=fallback)


def _replace_backticked_line(text: str, label: str, value: str) -> str:
    return re.sub(
        rf"(?m)^- {re.escape(label)}:\s*`[^`]*`$",
        f"- {label}: `{value}`",
        text,
    )


def _replace_plain_line(text: str, label: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^- {re.escape(label)}:\s*.*$")
    if pattern.search(text):
        return pattern.sub(f"- {label}: {value}", text)
    return text.rstrip() + f"\n- {label}: {value}\n"


def _parse_lifecycle_int(text: str, label: str) -> int:
    match = re.search(rf"(?m)^- {re.escape(label)}:\s*([0-9]+)", text)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _trust_level(total_interactions: int) -> str:
    if total_interactions >= 30:
        return "deep"
    if total_interactions >= 15:
        return "steady"
    if total_interactions >= 6:
        return "warming"
    return "early"


def _stage_name(*, days_active: int, total_interactions: int) -> str:
    if days_active >= 30 or total_interactions >= 40:
        return "deep"
    if days_active >= 14 or total_interactions >= 20:
        return "established"
    if days_active >= 7 or total_interactions >= 10:
        return "settling"
    if days_active >= 2 or total_interactions >= 4:
        return "early"
    return "onboarding"
