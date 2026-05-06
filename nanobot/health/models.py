"""Pydantic models for health onboarding submissions.

Extracted from the former health/api.py so that tools and workers can import
them without pulling in the full API surface.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from nanobot.health.storage import normalize_clock_time, validate_health_timezone


class Phase1Submission(BaseModel):
    full_name: str = ""
    location: str = ""
    email: str = ""
    phone: str = ""
    timezone: str = "UTC"
    language: str = "en"
    preferred_channel: str = "telegram"
    age_range: str = "not set"
    sex: str = "not set"
    gender: str = "not set"
    height_cm: float | None = None
    weight_kg: float | None = None
    known_conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    wake_time: str = ""
    sleep_time: str = ""
    consents: list[str] = Field(default_factory=list)

    @classmethod
    def __get_validators__(cls):  # type: ignore[override]
        yield cls._validate

    @classmethod
    def _validate(cls, v):  # type: ignore[override]
        return cls.model_validate(v)

    def model_post_init(self, __context) -> None:  # type: ignore[override]
        self.timezone = validate_health_timezone(self.timezone or "UTC")
        self.wake_time = normalize_clock_time(self.wake_time, field_name="wake_time")
        self.sleep_time = normalize_clock_time(self.sleep_time, field_name="sleep_time")


class Phase2Submission(BaseModel):
    mood_interest: int = Field(default=0, ge=0, le=3)
    mood_down: int = Field(default=0, ge=0, le=3)
    activity_level: str = "not set"
    nutrition_quality: str = "not set"
    sleep_quality: str = "not set"
    stress_level: str = "not set"
    goals: list[str] = Field(default_factory=list)
    current_concerns: str = ""
    reminder_preferences: list[str] = Field(default_factory=list)
    medication_reminder_windows: list[str] = Field(default_factory=list)
    morning_check_in: bool = True
    weekly_summary: bool = True


class OnboardingSubmission(BaseModel):
    phase1: Phase1Submission
    phase2: Phase2Submission
