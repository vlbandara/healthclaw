from __future__ import annotations

import json
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import StringSchema, tool_parameters_schema
from nanobot.observability.metrics import onboarding_completed_total


@tool_parameters(
    tool_parameters_schema(
        submission_json=StringSchema(
            "JSON string with top-level keys phase1 and phase2. "
            "phase1: full_name, location, email, phone, timezone, language, preferred_channel, "
            "age_range, sex, gender, height_cm, weight_kg, known_conditions, medications, "
            "allergies, wake_time, sleep_time, consents (array). "
            "phase2: mood_interest, mood_down (0-3), activity_level, nutrition_quality, "
            "sleep_quality, stress_level, goals (array), current_concerns, "
            "reminder_preferences, medication_reminder_windows, morning_check_in, weekly_summary.",
            min_length=20,
        ),
        required=["submission_json"],
    )
)
class CompleteOnboardingPlatformTool(Tool):
    """Finalize onboarding in platform mode (Postgres-backed), not filesystem-backed."""

    def __init__(
        self,
        *,
        tenant_id: str,
        session_key: str,
        memory_repo: Any,
        onboarding_repo: Any,
        pg_pool: Any,
    ):
        self._tenant_id = tenant_id
        self._session_key = session_key
        self._memory_repo = memory_repo
        self._onboarding_repo = onboarding_repo
        self._pg_pool = pg_pool

    @property
    def name(self) -> str:
        return "complete_onboarding"

    @property
    def description(self) -> str:
        return (
            "Call once you have gathered all required health onboarding information from the user. "
            "Pass submission_json: a JSON object {\"phase1\": {...}, \"phase2\": {...}} matching the "
            "schema in your system instructions. This persists profile + preferences for this account."
        )

    async def execute(self, submission_json: str, **kwargs: Any) -> str:
        from nanobot.health.api import OnboardingSubmission

        try:
            raw = json.loads(submission_json)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

        try:
            submission = OnboardingSubmission.model_validate(raw)
        except Exception as e:
            return f"Validation error (fix fields and retry): {e}"

        data = submission.model_dump()
        phase1 = data.get("phase1") or {}
        phase2 = data.get("phase2") or {}

        # Persist full structured profile.
        await self._memory_repo.save_document(self._tenant_id, "PROFILE", json.dumps(data, ensure_ascii=False, indent=2))

        # USER: stable human-facing facts.
        name = str(phase1.get("full_name") or "").strip()
        location = str(phase1.get("location") or "").strip()
        timezone = str(phase1.get("timezone") or "").strip()
        preferred = str(phase1.get("preferred_channel") or "").strip()

        user_lines = []
        if name:
            user_lines.append(f"Name: {name}")
        if location:
            user_lines.append(f"Location: {location}")
        if timezone:
            user_lines.append(f"Timezone: {timezone}")
        if preferred:
            user_lines.append(f"Preferred channel: {preferred}")
        await self._memory_repo.save_document(self._tenant_id, "USER", "\n".join(user_lines).strip())

        # MEMORY: small, coach-useful anchors.
        goals = phase2.get("goals") or []
        prefs = phase2.get("reminder_preferences") or []
        mem_lines = []
        if goals:
            mem_lines.append("Goals:")
            for g in goals[:8]:
                mem_lines.append(f"- {g}")
        if prefs:
            mem_lines.append("Reminder preferences:")
            for p in prefs[:12]:
                mem_lines.append(f"- {p}")
        concerns = str(phase2.get("current_concerns") or "").strip()
        if concerns:
            mem_lines.append("Current concerns:")
            mem_lines.append(concerns)
        await self._memory_repo.save_document(self._tenant_id, "MEMORY", "\n".join(mem_lines).strip())

        # Mark onboarding complete.
        await self._onboarding_repo.upsert_state(
            tenant_id=self._tenant_id,
            session_key=self._session_key,
            status="complete",
            phase="complete",
            draft_submission=data,
        )
        onboarding_completed_total.labels(channel=str(phase1.get("preferred_channel") or "telegram")).inc()

        # Create platform cron jobs for proactive check-ins (best-effort).
        try:
            preferred_channel = str(phase1.get("preferred_channel") or "telegram").strip() or "telegram"
            timezone = str(phase1.get("timezone") or "UTC").strip() or "UTC"
            chat_id = ""
            if preferred_channel == "telegram" and self._session_key.startswith("telegram:"):
                chat_id = self._session_key.split(":", 1)[1]
            morning = bool(phase2.get("morning_check_in"))
            weekly = bool(phase2.get("weekly_summary"))
            async with self._pg_pool.acquire() as conn:
                if morning and chat_id:
                    await conn.execute(
                        """
                        INSERT INTO cron_jobs (tenant_id, schedule, payload, next_run_at, enabled)
                        VALUES ($1::uuid, $2, $3::jsonb, now(), true)
                        """,
                        self._tenant_id,
                        "0 9 * * *",
                        json.dumps(
                            {
                                "kind": "morning_check_in",
                                "channel": preferred_channel,
                                "chat_id": chat_id,
                                "tz": timezone,
                            },
                            ensure_ascii=False,
                        ),
                    )
                if weekly and chat_id:
                    await conn.execute(
                        """
                        INSERT INTO cron_jobs (tenant_id, schedule, payload, next_run_at, enabled)
                        VALUES ($1::uuid, $2, $3::jsonb, now(), true)
                        """,
                        self._tenant_id,
                        "0 9 * * MON",
                        json.dumps(
                            {
                                "kind": "weekly_summary",
                                "channel": preferred_channel,
                                "chat_id": chat_id,
                                "tz": timezone,
                            },
                            ensure_ascii=False,
                        ),
                    )
        except Exception:
            # If scheduling fails, onboarding is still complete; user can proceed.
            pass

        return "Onboarding saved successfully. Confirm briefly and ask what they want to work on first."

