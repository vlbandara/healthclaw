from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from nanobot.health.continuity import (
    HealthContinuityFacts,
    TemporalContext,
    apply_health_continuity_updates,
    build_temporal_context,
    extract_health_continuity_facts,
    select_opening_style,
    select_variation_mode,
)


def test_extract_health_continuity_facts_from_explicit_text_and_voice() -> None:
    facts = extract_health_continuity_facts(
        (
            "Call me Vin. I wake up at 6:30 am and go to bed at 11 pm. "
            "Send me check-ins. I want to rebuild my sleep. "
            "I keep doomscrolling at night. Keep it brief."
        ),
        input_mode="voice",
    )

    assert facts.preferred_name == "Vin"
    assert facts.wake_time == "06:30"
    assert facts.sleep_time == "23:00"
    assert facts.proactive_enabled is True
    assert facts.voice_preferred is True
    assert facts.goals == ["Rebuild my sleep"]
    assert facts.friction_points == ["Doomscrolling at night"]
    assert facts.communication_preferences == ["Prefers brief replies."]


def test_build_temporal_context_tracks_gap_and_quiet_hours() -> None:
    temporal = build_temporal_context(
        timezone="UTC",
        last_seen_local_date="2026-04-12",
        now=datetime(2026, 4, 15, 23, 30, tzinfo=UTC),
    )

    assert temporal.local_date == "2026-04-15"
    assert temporal.weekday == "Wednesday"
    assert temporal.part_of_day == "late_night"
    assert temporal.quiet_hours is True
    assert temporal.days_since_last_user_message == 3
    assert temporal.first_touch_today is True


def test_variation_and_opening_styles_avoid_repeats() -> None:
    temporal = TemporalContext(
        timezone="UTC",
        local_timestamp="2026-04-15 14:00",
        local_date="2026-04-15",
        weekday="Wednesday",
        part_of_day="afternoon",
        quiet_hours=False,
        days_since_last_user_message=0,
        first_touch_today=False,
    )

    mode = select_variation_mode(
        user_text="I need a plan for this afternoon",
        temporal=temporal,
        recent_modes=["coach"],
    )
    opening_style = select_opening_style(
        temporal=temporal,
        recent_openings=["direct_open"],
        mode=mode,
    )

    assert mode != "coach"
    assert opening_style != "direct_open"


def test_apply_health_continuity_updates_refreshes_user_and_memory_files(tmp_path: Path) -> None:
    user_md = tmp_path / "USER.md"
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    memory_md = memory_dir / "MEMORY.md"

    user_md.write_text(
        (
            "# User Profile\n\n"
            "## Identity\n\n"
            "- User token: `U-demo`\n"
            "- Location: `not set`\n"
            "- Timezone: `UTC`\n"
            "- Language: `en`\n"
            "- Preferred channel: `telegram`\n\n"
            "## Goals\n\n"
            "- Gym consistency\n\n"
            "## Friction Points\n\n"
            "- No durable friction points recorded yet.\n\n"
            "## Current Concerns\n\n"
            "None\n\n"
            "## Daily Routine\n\n"
            "- Wake time: not set\n"
            "- Sleep time: not set\n"
            "- Reminder preferences: none\n\n"
            "## Communication Preferences\n\n"
            "- No explicit communication preferences recorded yet.\n"
        ),
        encoding="utf-8",
    )
    memory_md.write_text(
        (
            "# Long-term Memory\n\n"
            "## Lifecycle\n\n"
            "- Stage: onboarding\n"
            "- Days active: 1\n"
            "- Total interactions: 2\n"
            "- Streak: 1 days\n"
            "- Last mood trend: stable\n"
            "- Trust level: early\n"
            "- Last open loop: none\n"
        ),
        encoding="utf-8",
    )

    temporal = TemporalContext(
        timezone="Asia/Colombo",
        local_timestamp="2026-04-15 08:10",
        local_date="2026-04-15",
        weekday="Wednesday",
        part_of_day="morning",
        quiet_hours=False,
        days_since_last_user_message=1,
        first_touch_today=True,
    )
    facts = HealthContinuityFacts(
        open_loop="Do a 10 minute walk after lunch",
        friction_points=["Missing the late-night cutoff"],
        communication_preferences=["Prefers direct coaching."],
    )

    apply_health_continuity_updates(
        user_md=user_md,
        memory_md=memory_md,
        existing_profile={
            "location": "Colombo, Sri Lanka",
            "timezone": "Asia/Colombo",
            "preferred_channel": "telegram",
            "routines": {"wake_time": "06:30", "sleep_time": "22:30"},
            "goals": ["Gym consistency", "Protect sleep"],
        },
        temporal=temporal,
        facts=facts,
    )

    user_text = user_md.read_text(encoding="utf-8")
    memory_text = memory_md.read_text(encoding="utf-8")

    assert "- Location: `Colombo, Sri Lanka`" in user_text
    assert "- Timezone: `Asia/Colombo`" in user_text
    assert "- Wake time: 06:30" in user_text
    assert "- Sleep time: 22:30" in user_text
    assert "- Protect sleep" in user_text
    assert "- Missing the late-night cutoff" in user_text
    assert "- Prefers direct coaching." in user_text
    assert "- Days active: 2" in memory_text
    assert "- Total interactions: 3" in memory_text
    assert "- Streak: 2 days" in memory_text
    assert "- Last open loop: Do a 10 minute walk after lunch" in memory_text
