"""Health-profile tools that persist lightweight conversational preferences."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import BooleanSchema, StringSchema, tool_parameters_schema
from nanobot.health.storage import HealthWorkspace


@tool_parameters(
    tool_parameters_schema(
        preferred_name=StringSchema(
            "The short name or alias the user wants you to call them.",
            min_length=1,
            max_length=40,
        ),
        required=["preferred_name"],
    )
)
class SetPreferredNameTool(Tool):
    """Persist the user's preferred conversational name inside the encrypted vault."""

    def __init__(self, workspace: Path):
        self._health = HealthWorkspace(workspace)

    @property
    def name(self) -> str:
        return "set_preferred_name"

    @property
    def description(self) -> str:
        return (
            "Save the user's preferred name or alias in the encrypted health vault. "
            "Use this when the user tells you what they want to be called."
        )

    async def execute(self, preferred_name: str, **kwargs: Any) -> str:
        try:
            saved = self._health.save_preferred_name(preferred_name)
        except ValueError as exc:
            return f"Error: {exc}"
        return f"Saved preferred name: {saved}"


@tool_parameters(
    tool_parameters_schema(
        timezone=StringSchema(
            "Optional IANA timezone like 'Asia/Colombo' or 'America/New_York'.",
            min_length=3,
            nullable=True,
        ),
        location=StringSchema(
            "Optional city/region string to keep the profile local.",
            max_length=120,
            nullable=True,
        ),
        wake_time=StringSchema(
            "Optional wake time in 24-hour HH:MM format.",
            min_length=4,
            max_length=5,
            nullable=True,
        ),
        sleep_time=StringSchema(
            "Optional sleep time in 24-hour HH:MM format.",
            min_length=4,
            max_length=5,
            nullable=True,
        ),
        preferred_name=StringSchema(
            "Optional short name or alias the user wants you to use.",
            min_length=1,
            max_length=40,
            nullable=True,
        ),
        preferred_channel=StringSchema(
            "Optional preferred channel: telegram or whatsapp.",
            enum=["telegram", "whatsapp"],
            nullable=True,
        ),
        proactive_enabled=BooleanSchema(
            description="Optional preference for lightweight proactive check-ins and follow-ups.",
            nullable=True,
        ),
        voice_preferred=BooleanSchema(
            description="Optional preference for voice-note style interactions.",
            nullable=True,
        ),
        last_seen_local_date=StringSchema(
            "Optional last local interaction date in YYYY-MM-DD format.",
            min_length=10,
            max_length=10,
            nullable=True,
        ),
    )
)
class UpdateHealthProfileTool(Tool):
    """Persist lightweight health profile edits from normal conversation."""

    def __init__(self, workspace: Path):
        self._health = HealthWorkspace(workspace)

    @property
    def name(self) -> str:
        return "update_health_profile"

    @property
    def description(self) -> str:
        return (
            "Update lightweight health profile fields like timezone, location, wake_time, "
            "sleep_time, preferred_name, preferred_channel, proactive_enabled, "
            "voice_preferred, or last_seen_local_date."
        )

    async def execute(
        self,
        timezone: str | None = None,
        location: str | None = None,
        wake_time: str | None = None,
        sleep_time: str | None = None,
        preferred_name: str | None = None,
        preferred_channel: str | None = None,
        proactive_enabled: bool | None = None,
        voice_preferred: bool | None = None,
        last_seen_local_date: str | None = None,
        **kwargs: Any,
    ) -> str:
        if all(
            value is None
            for value in (
                timezone,
                location,
                wake_time,
                sleep_time,
                preferred_name,
                preferred_channel,
                proactive_enabled,
                voice_preferred,
                last_seen_local_date,
            )
        ):
            return (
                "Error: provide at least one field to update: timezone, location, wake_time, "
                "sleep_time, preferred_name, preferred_channel, proactive_enabled, "
                "voice_preferred, or last_seen_local_date."
            )

        try:
            changed = self._health.update_profile(
                timezone=timezone,
                location=location,
                wake_time=wake_time,
                sleep_time=sleep_time,
                preferred_name=preferred_name,
                preferred_channel=preferred_channel,
                proactive_enabled=proactive_enabled,
                voice_preferred=voice_preferred,
                last_seen_local_date=last_seen_local_date,
            )
        except ValueError as exc:
            return f"Error: {exc}"

        if not changed:
            return "No profile changes were needed."
        parts = [f"{key}={value}" for key, value in changed.items()]
        return "Updated health profile: " + ", ".join(parts)
