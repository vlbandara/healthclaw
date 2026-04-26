from __future__ import annotations

from prometheus_client import Counter, Histogram

agent_turns_total = Counter(
    "nanobot_agent_turns_total",
    "Total agent turns processed",
    ["status", "channel"],
)

agent_turn_duration_seconds = Histogram(
    "nanobot_agent_turn_duration_seconds",
    "Agent turn duration in seconds",
    ["channel"],
)

onboarding_started_total = Counter(
    "nanobot_onboarding_started_total",
    "Total onboarding sessions started (token redeemed)",
    ["channel"],
)

onboarding_completed_total = Counter(
    "nanobot_onboarding_completed_total",
    "Total onboarding sessions completed (complete_onboarding tool)",
    ["channel"],
)

