"""Agent-callable wearable data tools for the health workspace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import StringSchema, tool_parameters_schema
from nanobot.health.openwearables import (
    WearableSnapshot,
    openwearables_enabled,
    sync_wearable_snapshot,
)
from nanobot.health.storage import HealthWorkspace, get_health_vault_secret

_NO_DATA = "No wearable data yet — ask the user to connect a wearable in setup."
_NOT_CONFIGURED = "Wearables are not configured on this host."


def _load_snapshot(health: HealthWorkspace) -> WearableSnapshot | None:
    try:
        secret = get_health_vault_secret()
    except Exception:
        secret = None
    return WearableSnapshot.from_dict(health.load_wearables_cache(secret=secret) or {})


class GetSleepSummaryTool(Tool):
    """Return the latest cached sleep summary from the user's wearable."""

    def __init__(self, workspace: Path):
        self._health = HealthWorkspace(workspace)

    @property
    def name(self) -> str:
        return "get_sleep_summary"

    @property
    def description(self) -> str:
        return (
            "Return the most recent sleep summary from the user's connected wearable — "
            "score, duration, efficiency, and date. Use when the user asks about sleep quality or last night's rest."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        snapshot = _load_snapshot(self._health)
        if not snapshot:
            return _NO_DATA
        summary = snapshot.summaries.get("sleep") or {}
        if not summary:
            return _NO_DATA
        return json.dumps(summary)


class GetRecoverySummaryTool(Tool):
    """Return the latest cached recovery summary from the user's wearable."""

    def __init__(self, workspace: Path):
        self._health = HealthWorkspace(workspace)

    @property
    def name(self) -> str:
        return "get_recovery_summary"

    @property
    def description(self) -> str:
        return (
            "Return the most recent recovery summary from the user's connected wearable — "
            "recovery score, HRV, and resting heart rate. Use when the user asks about readiness, HRV, or recovery."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        snapshot = _load_snapshot(self._health)
        if not snapshot:
            return _NO_DATA
        summary = snapshot.summaries.get("recovery") or {}
        if not summary:
            return _NO_DATA
        return json.dumps(summary)


class GetActivitySummaryTool(Tool):
    """Return the latest cached activity summary from the user's wearable."""

    def __init__(self, workspace: Path):
        self._health = HealthWorkspace(workspace)

    @property
    def name(self) -> str:
        return "get_activity_summary"

    @property
    def description(self) -> str:
        return (
            "Return the most recent activity summary from the user's connected wearable — "
            "steps, active minutes, and calories. Use when the user asks about movement, steps, or activity."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        snapshot = _load_snapshot(self._health)
        if not snapshot:
            return _NO_DATA
        summary = snapshot.summaries.get("activity") or {}
        if not summary:
            return _NO_DATA
        return json.dumps(summary)


class GetBodySummaryTool(Tool):
    """Return the latest cached body metrics from the user's wearable."""

    def __init__(self, workspace: Path):
        self._health = HealthWorkspace(workspace)

    @property
    def name(self) -> str:
        return "get_body_summary"

    @property
    def description(self) -> str:
        return (
            "Return the most recent body metrics from the user's connected wearable — "
            "weight, body fat percentage, resting heart rate. Use when the user asks about body composition or weight."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        snapshot = _load_snapshot(self._health)
        if not snapshot:
            return _NO_DATA
        summary = snapshot.summaries.get("body") or {}
        if not summary:
            return _NO_DATA
        return json.dumps(summary)


class ListWearableConnectionsTool(Tool):
    """List the user's connected wearable providers and sync status."""

    def __init__(self, workspace: Path):
        self._health = HealthWorkspace(workspace)

    @property
    def name(self) -> str:
        return "list_wearable_connections"

    @property
    def description(self) -> str:
        return (
            "Return the list of connected wearable providers, last sync time, and data freshness. "
            "Use when the user asks which wearables are connected or whether data is up to date."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        snapshot = _load_snapshot(self._health)
        if not snapshot:
            return _NO_DATA
        return json.dumps(
            {
                "connected_providers": snapshot.connected_providers,
                "last_sync_at": snapshot.last_sync_at,
                "freshness": snapshot.freshness,
                "freshness_note": snapshot.freshness_note,
            }
        )


@tool_parameters(
    tool_parameters_schema(
        provider=StringSchema(
            "Optional provider slug to sync (e.g. 'fitbit', 'garmin'). Omit to sync all active providers.",
            nullable=True,
        ),
    )
)
class SyncWearablesTool(Tool):
    """Trigger a live wearable data refresh and return the updated snapshot."""

    def __init__(self, workspace: Path):
        self._health = HealthWorkspace(workspace)

    @property
    def name(self) -> str:
        return "sync_wearables"

    @property
    def description(self) -> str:
        return (
            "Trigger a live sync from the user's connected wearable provider(s) and return fresh data. "
            "Use when the user asks to refresh their data or when the cached snapshot is stale. "
            "Specify a provider slug to sync only that device, or omit to sync all active connections."
        )

    async def execute(self, provider: str | None = None, **kwargs: Any) -> str:
        if not openwearables_enabled():
            return _NOT_CONFIGURED
        try:
            secret = get_health_vault_secret()
        except Exception:
            secret = None
        try:
            snapshot = await sync_wearable_snapshot(
                self._health,
                provider=provider or None,
                secret=secret,
            )
        except ValueError as exc:
            return str(exc)
        except Exception as exc:
            return f"Sync failed: {exc}"
        return json.dumps(snapshot.to_dict())
