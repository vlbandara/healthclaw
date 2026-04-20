#!/usr/bin/env python3
"""Seed a returning-user health demo workspace for local rehearsal."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from nanobot.health.bootstrap import persist_health_onboarding
from nanobot.health.continuity import (
    HealthContinuityFacts,
    TemporalContext,
    apply_health_continuity_updates,
)
from nanobot.health.storage import HealthWorkspace
from nanobot.session.manager import Session, SessionManager


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Workspace directory to seed.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("examples/health/demo_fixture.json"),
        help="Fixture JSON to apply.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the target workspace if it already exists.",
    )
    return parser.parse_args()


def _load_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _prepare_workspace(path: Path, *, force: bool) -> None:
    if path.exists() and force:
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _replace_memory_line(text: str, label: str, value: str) -> str:
    import re

    pattern = re.compile(rf"(?m)^- {re.escape(label)}:\s*.*$")
    replacement = f"- {label}: {value}"
    if pattern.search(text):
        return pattern.sub(replacement, text)
    return text.rstrip() + "\n" + replacement + "\n"


def _seed_memory_files(workspace: Path, fixture: dict, profile: dict) -> None:
    continuity = fixture.get("continuity") or {}
    apply_health_continuity_updates(
        user_md=workspace / "USER.md",
        memory_md=workspace / "memory" / "MEMORY.md",
        existing_profile=profile,
        temporal=TemporalContext(
            timezone=profile.get("timezone", "UTC"),
            local_timestamp="2026-04-15 07:10",
            local_date="2026-04-15",
            weekday="Wednesday",
            part_of_day="morning",
            quiet_hours=False,
            days_since_last_user_message=1,
            first_touch_today=True,
        ),
        facts=HealthContinuityFacts(
            friction_points=list(continuity.get("friction_points") or []),
            communication_preferences=list(continuity.get("communication_preferences") or []),
            open_loop=str(continuity.get("open_loop") or "").strip() or None,
        ),
    )

    memory_path = workspace / "memory" / "MEMORY.md"
    memory_text = memory_path.read_text(encoding="utf-8")
    lifecycle = fixture.get("lifecycle") or {}
    memory_text = _replace_memory_line(memory_text, "Stage", str(lifecycle.get("stage") or "settling"))
    memory_text = _replace_memory_line(memory_text, "Days active", str(lifecycle.get("days_active") or 4))
    memory_text = _replace_memory_line(memory_text, "Total interactions", str(lifecycle.get("total_interactions") or 9))
    memory_text = _replace_memory_line(memory_text, "Streak", f"{int(lifecycle.get('streak') or 2)} days")
    memory_text = _replace_memory_line(memory_text, "Trust level", str(lifecycle.get("trust_level") or "warming"))
    memory_text = _replace_memory_line(
        memory_text,
        "Last open loop",
        str(continuity.get("open_loop") or "none"),
    )
    memory_path.write_text(memory_text.rstrip() + "\n", encoding="utf-8")


def _seed_history(workspace: Path, fixture: dict) -> None:
    history_path = workspace / "memory" / "history.jsonl"
    summary = fixture.get("historySummary") or {}
    entry = {
        "cursor": 1,
        "timestamp": summary.get("timestamp") or "2026-04-14T18:45:00+05:30",
        "content": summary.get("content") or "",
    }
    history_path.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")


def _seed_session(workspace: Path, fixture: dict) -> None:
    session_fixture = fixture.get("session") or {}
    manager = SessionManager(workspace)
    session = Session(key=str(session_fixture.get("key") or "telegram:demo-telegram-chat"))
    for message in session_fixture.get("messages") or []:
        session.messages.append(dict(message))
    manager.save(session)


def main() -> None:
    args = _parse_args()
    fixture = _load_fixture(args.fixture)
    _prepare_workspace(args.workspace, force=args.force)

    persist_health_onboarding(
        args.workspace,
        fixture["submission"],
        invite=fixture.get("invite"),
        user_token=fixture.get("userToken"),
    )

    health = HealthWorkspace(args.workspace)
    patch = fixture.get("profilePatch") or {}
    health.update_profile(
        proactive_enabled=patch.get("proactive_enabled"),
        voice_preferred=patch.get("voice_preferred"),
        last_seen_local_date=patch.get("last_seen_local_date"),
    )
    profile = health.load_profile() or {}
    profile["friction_points"] = list((fixture.get("continuity") or {}).get("friction_points") or [])
    profile["communication_preferences"] = list((fixture.get("continuity") or {}).get("communication_preferences") or [])
    profile["last_open_loop"] = str((fixture.get("continuity") or {}).get("open_loop") or "none")
    health.save_profile(profile)

    _seed_memory_files(args.workspace, fixture, profile)
    _seed_history(args.workspace, fixture)
    _seed_session(args.workspace, fixture)

    print(f"Seeded health demo workspace at {args.workspace}")
    print(f"Fixture: {args.fixture}")
    print("Suggested session key: telegram:demo-telegram-chat")


if __name__ == "__main__":
    main()
