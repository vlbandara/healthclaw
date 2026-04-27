"""Generate health-specific workspace assets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from nanobot.health.storage import derive_preferred_name
from nanobot.utils.helpers import ensure_dir
from nanobot.utils.prompt_templates import render_template


def read_tenant_user_token(workspace: Path) -> str | None:
    """Optional per-tenant token from ``.tenant_meta.json`` (multi-tenant gateway)."""
    path = workspace / ".tenant_meta.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tok = data.get("user_token")
        return tok if isinstance(tok, str) and tok.strip() else None
    except Exception:
        return None


def _clean_list(values: list[str] | None) -> list[str]:
    return [value.strip() for value in values or [] if value and value.strip()]


def _bullet_lines(values: list[str], fallback: str) -> str:
    cleaned = _clean_list(values)
    if not cleaned:
        return f"- {fallback}"
    return "\n".join(f"- {value}" for value in cleaned)


def _string_list_or_fallback(values: list[str], fallback: str) -> str:
    cleaned = _clean_list(values)
    return ", ".join(cleaned) if cleaned else fallback


def render_health_heartbeat(profile: dict[str, Any]) -> str:
    prefs = profile.get("preferences", {})
    routines = profile.get("routines", {})
    wake_time = routines.get("wake_time") or "07:00"
    sleep_time = routines.get("sleep_time") or "22:30"
    reminder_windows = _clean_list(prefs.get("medication_reminder_windows"))
    goals = _clean_list(profile.get("goals"))
    concerns = profile.get("current_concerns") or "No current concern was provided during onboarding."
    return render_template(
        "health/HEARTBEAT.md",
        wake_time=wake_time,
        sleep_time=sleep_time,
        reminder_windows=reminder_windows,
        morning_check_in=bool(prefs.get("morning_check_in", True)),
        weekly_summary=bool(prefs.get("weekly_summary", True)),
        goals=goals,
        concerns=concerns,
    )


def render_health_user(profile: dict[str, Any]) -> str:
    demographics = profile.get("demographics", {})
    routines = profile.get("routines", {})
    preferences = profile.get("preferences", {})
    friction_points = profile.get("friction_points") or []
    communication_preferences = profile.get("communication_preferences") or []
    return render_template(
        "health/USER.md",
        user_token=profile.get("user_token", "USER-001"),
        location=profile.get("location", "not set"),
        timezone=profile.get("timezone", "UTC"),
        language=profile.get("language", "en"),
        preferred_channel=profile.get("preferred_channel", "telegram"),
        age_range=demographics.get("age_range", "not set"),
        sex=demographics.get("sex", "not set"),
        gender=demographics.get("gender", "not set"),
        height_cm=demographics.get("height_cm", "not set"),
        weight_kg=demographics.get("weight_kg", "not set"),
        known_conditions=_bullet_lines(
            demographics.get("known_conditions"),
            "No known conditions were disclosed.",
        ),
        medications=_bullet_lines(
            demographics.get("medications"),
            "No active medications were disclosed.",
        ),
        allergies=_bullet_lines(
            demographics.get("allergies"),
            "No allergies were disclosed.",
        ),
        goals=_bullet_lines(profile.get("goals"), "Goals still need to be refined."),
        current_concerns=profile.get("current_concerns") or "No current concerns were recorded.",
        reminder_preferences=_string_list_or_fallback(
            preferences.get("reminder_preferences"),
            "No reminder preferences were specified.",
        ),
        wake_time=routines.get("wake_time", "not set"),
        sleep_time=routines.get("sleep_time", "not set"),
        friction_points=_bullet_lines(
            friction_points,
            "No durable friction points recorded yet.",
        ),
        communication_preferences=_bullet_lines(
            communication_preferences,
            "No explicit communication preferences recorded yet.",
        ),
    )


def render_health_memory(profile: dict[str, Any]) -> str:
    screenings = profile.get("screenings", {})
    return render_template(
        "health/memory/MEMORY.md",
        mood_interest=screenings.get("mood_interest", 0),
        mood_down=screenings.get("mood_down", 0),
        activity_level=profile.get("wellbeing", {}).get("activity_level", "not set"),
        nutrition_quality=profile.get("wellbeing", {}).get("nutrition_quality", "not set"),
        sleep_quality=profile.get("wellbeing", {}).get("sleep_quality", "not set"),
        stress_level=profile.get("wellbeing", {}).get("stress_level", "not set"),
        last_open_loop=profile.get("last_open_loop", "none"),
    )


def refresh_health_workspace_assets(
    workspace: Path,
    profile: dict[str, Any],
    *,
    include_memory: bool = False,
) -> None:
    """Refresh rendered health workspace files derived from the saved profile."""
    ensure_dir(workspace)
    ensure_dir(workspace / "memory")
    files: dict[Path, str] = {
        workspace / "USER.md": render_health_user(profile),
        workspace / "HEARTBEAT.md": render_health_heartbeat(profile),
    }
    if include_memory:
        files[workspace / "memory" / "MEMORY.md"] = render_health_memory(profile)

    for path, content in files.items():
        path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_health_workspace_assets(workspace: Path, profile: dict[str, Any]) -> None:
    """Render health-specific files into the workspace."""
    ensure_dir(workspace)
    ensure_dir(workspace / "memory")
    skill_names = [
        "focus-learning",
        "habits",
        "health",
        "health-checkin",
        "life-admin",
        "medication-support",
        "movement-recovery",
        "nutrition-support",
        "personal-growth",
        "sleep-support",
        "stress-reset",
    ]
    for skill_name in skill_names:
        ensure_dir(workspace / "skills" / skill_name)

    files: dict[Path, str] = {
        workspace / "AGENTS.md": render_template("health/AGENTS.md"),
        workspace / "SOUL.md": render_template("health/SOUL.md"),
        workspace / "USER.md": render_health_user(profile),
        workspace / "HEARTBEAT.md": render_health_heartbeat(profile),
        workspace / "memory" / "MEMORY.md": render_health_memory(profile),
        workspace / "skills" / "health" / "SKILL.md": render_template("health/skills/health/SKILL.md"),
        workspace / "skills" / "health-checkin" / "SKILL.md": render_template(
            "health/skills/health-checkin/SKILL.md"
        ),
        workspace / "skills" / "habits" / "SKILL.md": render_template("health/skills/habits/SKILL.md"),
        workspace / "skills" / "sleep-support" / "SKILL.md": render_template(
            "health/skills/sleep-support/SKILL.md"
        ),
        workspace / "skills" / "stress-reset" / "SKILL.md": render_template(
            "health/skills/stress-reset/SKILL.md"
        ),
        workspace / "skills" / "medication-support" / "SKILL.md": render_template(
            "health/skills/medication-support/SKILL.md"
        ),
        workspace / "skills" / "movement-recovery" / "SKILL.md": render_template(
            "health/skills/movement-recovery/SKILL.md"
        ),
        workspace / "skills" / "nutrition-support" / "SKILL.md": render_template(
            "health/skills/nutrition-support/SKILL.md"
        ),
        workspace / "skills" / "personal-growth" / "SKILL.md": render_template(
            "health/skills/personal-growth/SKILL.md"
        ),
        workspace / "skills" / "focus-learning" / "SKILL.md": render_template(
            "health/skills/focus-learning/SKILL.md"
        ),
        workspace / "skills" / "life-admin" / "SKILL.md": render_template(
            "health/skills/life-admin/SKILL.md"
        ),
    }

    for path, content in files.items():
        path.write_text(content.rstrip() + "\n", encoding="utf-8")

    history_path = workspace / "memory" / "history.jsonl"
    if not history_path.exists():
        history_path.write_text("", encoding="utf-8")

    try:
        from nanobot.utils.gitstore import GitStore

        GitStore(
            workspace,
            tracked_files=["SOUL.md", "USER.md", "memory/MEMORY.md"],
        ).init()
    except Exception:
        pass


def build_profile_payload(submission: dict[str, Any], *, channel: str, user_token: str) -> dict[str, Any]:
    """Build the pseudonymized health profile written to disk."""
    phase1 = submission["phase1"]
    phase2 = submission["phase2"]
    wearables_seed = submission.get("_wearables") or {}
    return {
        "mode": "health",
        "user_token": user_token,
        "preferred_channel": phase1["preferred_channel"],
        "location": phase1.get("location", "").strip(),
        "timezone": phase1["timezone"],
        "language": phase1["language"],
        "demographics": {
            "age_range": phase1["age_range"],
            "sex": phase1["sex"],
            "gender": phase1["gender"],
            "height_cm": phase1.get("height_cm"),
            "weight_kg": phase1.get("weight_kg"),
            "known_conditions": _clean_list(phase1.get("known_conditions")),
            "medications": _clean_list(phase1.get("medications")),
            "allergies": _clean_list(phase1.get("allergies")),
        },
        "routines": {
            "wake_time": phase1.get("wake_time"),
            "sleep_time": phase1.get("sleep_time"),
        },
        "screenings": {
            "mood_interest": phase2["mood_interest"],
            "mood_down": phase2["mood_down"],
        },
        "wellbeing": {
            "activity_level": phase2["activity_level"],
            "nutrition_quality": phase2["nutrition_quality"],
            "sleep_quality": phase2["sleep_quality"],
            "stress_level": phase2["stress_level"],
        },
        "goals": _clean_list(phase2.get("goals")),
        "current_concerns": phase2.get("current_concerns", "").strip(),
        "preferences": {
            "morning_check_in": bool(phase2.get("morning_check_in", True)),
            "reminder_preferences": _clean_list(phase2.get("reminder_preferences")),
            "medication_reminder_windows": _clean_list(
                phase2.get("medication_reminder_windows")
            ),
            "weekly_summary": bool(phase2.get("weekly_summary", True)),
        },
        "friction_points": [],
        "communication_preferences": [],
        "proactive_enabled": False,
        "voice_preferred": False,
        "last_seen_local_date": "",
        "last_open_loop": "none",
        "wearables": {
            "enabled": bool(wearables_seed.get("enabled")),
            "preferred_providers": _clean_list(
                wearables_seed.get("preferred_providers") or wearables_seed.get("connected_providers")
            ),
            "use_for_coaching": bool(wearables_seed.get("use_for_coaching", False)),
        },
        "channel_binding": {
            "preferred_channel": phase1["preferred_channel"],
            "invite_channel": channel,
        },
    }


def build_vault_payload(
    submission: dict[str, Any],
    invite: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the encrypted vault payload with raw identifiers."""
    invite = invite or {}
    phase1 = submission["phase1"]
    full_name = phase1["full_name"]
    preferred_name = derive_preferred_name(full_name)
    identifiers = {
        "person_names": _clean_list([full_name, preferred_name]),
        "emails": _clean_list([phase1.get("email", "")]),
        "phones": _clean_list([phase1.get("phone", "")]),
        "chat_ids": _clean_list([invite.get("chat_id", "")]),
        "channels": _clean_list([invite.get("channel", "")]),
    }
    return {
        "identifiers": identifiers,
        "contact": {
            "full_name": full_name,
            "preferred_name": preferred_name,
            "location": phase1.get("location", "").strip(),
            "email": phase1.get("email", "").strip(),
            "phone": phase1.get("phone", "").strip(),
            "invite_channel": invite.get("channel"),
            "invite_chat_id": invite.get("chat_id"),
        },
        "consents": submission["phase1"]["consents"],
    }


def persist_health_onboarding(
    workspace: Path,
    submission: dict[str, Any],
    *,
    invite: dict[str, Any] | None = None,
    secret: str | None = None,
    user_token: str | None = None,
    stable_token_hint: str | None = None,
) -> dict[str, Any]:
    """Write profile, encrypted vault, and rendered workspace assets."""
    from nanobot.health.storage import HealthWorkspace

    health = HealthWorkspace(workspace)
    existing_profile = health.load_profile() or {}
    invite_meta = invite or {
        "channel": submission.get("phase1", {}).get("preferred_channel", ""),
        "chat_id": "",
    }
    user_token = _resolve_user_token(
        explicit=user_token,
        existing=existing_profile.get("user_token"),
        tenant=read_tenant_user_token(workspace),
        invite=invite_meta,
        stable_hint=stable_token_hint,
    )
    profile = build_profile_payload(
        submission,
        channel=invite_meta.get("channel", ""),
        user_token=user_token,
    )
    vault = build_vault_payload(submission, invite_meta)
    health.save_profile(profile)
    health.save_vault(vault, secret=secret)
    wearables_seed = submission.get("_wearables")
    if isinstance(wearables_seed, dict) and wearables_seed:
        health.apply_wearables_seed(wearables_seed, secret=secret)
    write_health_workspace_assets(workspace, profile)
    pending = workspace / ".health_chat_onboarding"
    if pending.exists():
        try:
            pending.unlink()
        except OSError:
            pass
    return profile


def _resolve_user_token(
    *,
    explicit: str | None,
    existing: str | None,
    tenant: str | None,
    invite: dict[str, Any],
    stable_hint: str | None,
) -> str:
    for candidate in (explicit, existing, tenant, stable_hint):
        cleaned = str(candidate or "").strip()
        if cleaned:
            return cleaned
    channel = str(invite.get("channel") or "").strip()
    chat_id = str(invite.get("chat_id") or "").strip()
    if channel and chat_id:
        digest = hashlib.sha256(f"{channel}:{chat_id}".encode("utf-8")).hexdigest()[:12]
        return f"U-{digest}"
    raise ValueError("Unable to resolve a stable health user token for onboarding.")
