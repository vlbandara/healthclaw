"""Open Wearables integration primitives for Healthclaw."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from nanobot.health.storage import HealthWorkspace

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in _TRUE_VALUES


def _clean_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def _coerce_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "results", "data", "connections", "providers"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload]


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _pick_latest(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {}

    def _sort_key(item: dict[str, Any]) -> tuple[float, str]:
        for key in (
            "date",
            "day",
            "summary_date",
            "start_date",
            "start_time",
            "created_at",
            "updated_at",
            "timestamp",
        ):
            parsed = _parse_dt(item.get(key))
            if parsed is not None:
                return (parsed.timestamp(), key)
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                return (0.0, raw.strip())
        return (0.0, "")

    return sorted(items, key=_sort_key, reverse=True)[0]


def _find_number(payload: dict[str, Any], *keys: str) -> float | int | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                parsed = float(value)
            except ValueError:
                continue
            if parsed.is_integer():
                return int(parsed)
            return parsed
    return None


def _find_date(payload: dict[str, Any]) -> str:
    for key in ("date", "day", "summary_date", "start_date", "start_time", "timestamp"):
        value = payload.get(key)
        if value:
            return str(value)
    return ""


def _compact_summary(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    latest = _pick_latest(_coerce_items(payload))
    if not latest:
        return {}
    compact: dict[str, Any] = {"date": _find_date(latest)}
    if kind == "sleep":
        compact["score"] = _find_number(latest, "score", "sleep_score", "sleep_quality")
        compact["duration_h"] = _find_number(
            latest,
            "duration_h",
            "sleep_duration_hours",
            "total_sleep_hours",
            "total_sleep_duration_hours",
        )
        duration_s = _find_number(
            latest,
            "duration_seconds",
            "sleep_duration_seconds",
            "total_sleep_seconds",
            "total_sleep_duration_seconds",
        )
        if compact.get("duration_h") is None and isinstance(duration_s, (int, float)):
            compact["duration_h"] = round(float(duration_s) / 3600.0, 2)
        compact["efficiency"] = _find_number(latest, "efficiency", "sleep_efficiency")
    elif kind == "activity":
        compact["steps"] = _find_number(latest, "steps", "step_count")
        compact["active_minutes"] = _find_number(
            latest,
            "active_minutes",
            "activity_minutes",
            "moderate_vigorous_minutes",
        )
        compact["calories"] = _find_number(latest, "calories", "active_calories", "energy_burned")
    elif kind == "recovery":
        compact["score"] = _find_number(latest, "score", "recovery_score")
        compact["hrv"] = _find_number(latest, "hrv", "hrv_ms", "hrv_rmssd")
        compact["resting_hr"] = _find_number(latest, "resting_hr", "resting_heart_rate", "rhr")
    elif kind == "body":
        compact["weight_kg"] = _find_number(latest, "weight_kg", "weight", "body_weight")
        compact["body_fat_pct"] = _find_number(latest, "body_fat_pct", "body_fat_percentage")
        compact["resting_hr"] = _find_number(latest, "resting_hr", "resting_heart_rate", "rhr")
    else:
        for key, value in latest.items():
            if isinstance(value, (str, int, float)) and key not in compact:
                compact[key] = value
    return {key: value for key, value in compact.items() if value not in (None, "", [])}


def _compact_health_scores(payload: Any) -> dict[str, Any]:
    items = _coerce_items(payload)
    latest = _pick_latest(items)
    if not latest:
        return {}
    data: dict[str, Any] = {"date": _find_date(latest)}
    for key in (
        "sleep",
        "sleep_score",
        "recovery",
        "recovery_score",
        "strain",
        "stress",
        "energy",
        "energy_score",
        "hrv",
        "hrv_index",
    ):
        value = _find_number(latest, key)
        if value is not None:
            data[key] = value
    return data


def _summary_delta(kind: str, items: list[dict[str, Any]]) -> str | None:
    ordered = sorted(
        _coerce_items(items),
        key=lambda item: (_parse_dt(item.get("date") or item.get("start_time") or item.get("timestamp")) or datetime.min.replace(tzinfo=UTC)),
        reverse=True,
    )
    if len(ordered) < 2:
        return None
    latest = _compact_summary(kind, [ordered[0]])
    previous = _compact_summary(kind, [ordered[1]])
    if kind == "sleep":
        latest_score = latest.get("score")
        previous_score = previous.get("score")
        if isinstance(latest_score, (int, float)) and isinstance(previous_score, (int, float)):
            if latest_score >= previous_score + 5:
                return "sleep score improved versus the prior day"
            if latest_score <= previous_score - 5:
                return "sleep score declined versus the prior day"
    if kind == "activity":
        latest_steps = latest.get("steps")
        previous_steps = previous.get("steps")
        if isinstance(latest_steps, (int, float)) and isinstance(previous_steps, (int, float)):
            if latest_steps >= previous_steps * 1.2:
                return "activity rose noticeably versus the prior day"
            if latest_steps <= previous_steps * 0.8:
                return "activity fell noticeably versus the prior day"
    if kind == "recovery":
        latest_score = latest.get("score")
        previous_score = previous.get("score")
        if isinstance(latest_score, (int, float)) and isinstance(previous_score, (int, float)):
            if latest_score >= previous_score + 5:
                return "recovery improved versus the prior day"
            if latest_score <= previous_score - 5:
                return "recovery declined versus the prior day"
    return None


@dataclass(slots=True)
class WearableSnapshot:
    """Compact wearable context safe to inject into prompts."""

    generated_at: str
    connected_providers: list[str] = field(default_factory=list)
    last_sync_at: str = ""
    freshness: str = "unknown"
    freshness_note: str = ""
    summaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    health_scores: dict[str, Any] = field(default_factory=dict)
    trend_flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> WearableSnapshot | None:
        if not isinstance(payload, dict):
            return None
        return cls(
            generated_at=str(payload.get("generated_at") or ""),
            connected_providers=list(payload.get("connected_providers") or []),
            last_sync_at=str(payload.get("last_sync_at") or ""),
            freshness=str(payload.get("freshness") or "unknown"),
            freshness_note=str(payload.get("freshness_note") or ""),
            summaries=dict(payload.get("summaries") or {}),
            health_scores=dict(payload.get("health_scores") or {}),
            trend_flags=list(payload.get("trend_flags") or []),
            notes=list(payload.get("notes") or []),
        )

    def context_lines(self) -> list[str]:
        lines: list[str] = []
        providers = ", ".join(self.connected_providers) if self.connected_providers else "none"
        lines.append(f"Connected Providers: {providers}")
        if self.last_sync_at:
            lines.append(f"Last Sync At: {self.last_sync_at}")
        if self.freshness_note:
            lines.append(f"Data Freshness: {self.freshness_note}")
        for label, key in (
            ("Sleep Summary", "sleep"),
            ("Activity Summary", "activity"),
            ("Recovery Summary", "recovery"),
            ("Body Summary", "body"),
        ):
            summary = self.summaries.get(key) or {}
            if summary:
                lines.append(f"{label}: {summary}")
        if self.health_scores:
            lines.append(f"Health Scores: {self.health_scores}")
        if self.trend_flags:
            lines.append(f"Trend Flags: {', '.join(self.trend_flags)}")
        if self.notes:
            lines.append(f"Wearable Notes: {', '.join(self.notes)}")
        return lines


@dataclass(slots=True)
class OpenWearablesClientConfig:
    """Environment-backed client configuration."""

    api_url: str
    api_key: str
    timeout_seconds: float = 20.0
    sync_window_days: int = 3
    stale_after_hours: int = 36

    @classmethod
    def from_env(cls) -> OpenWearablesClientConfig | None:
        api_url = _clean_url(os.environ.get("OPENWEARABLES_API_URL", ""))
        api_key = str(os.environ.get("OPENWEARABLES_API_KEY", "")).strip()
        if not api_url or not api_key:
            return None
        timeout_raw = str(os.environ.get("OPENWEARABLES_TIMEOUT_SECONDS", "20")).strip()
        window_raw = str(os.environ.get("OPENWEARABLES_SYNC_WINDOW_DAYS", "3")).strip()
        stale_raw = str(os.environ.get("OPENWEARABLES_STALE_AFTER_HOURS", "36")).strip()
        try:
            timeout_seconds = max(5.0, float(timeout_raw))
        except ValueError:
            timeout_seconds = 20.0
        try:
            sync_window_days = max(1, int(window_raw))
        except ValueError:
            sync_window_days = 3
        try:
            stale_after_hours = max(1, int(stale_raw))
        except ValueError:
            stale_after_hours = 36
        return cls(
            api_url=api_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            sync_window_days=sync_window_days,
            stale_after_hours=stale_after_hours,
        )


def openwearables_enabled() -> bool:
    config = OpenWearablesClientConfig.from_env()
    if config is None:
        return False
    raw = os.environ.get("OPENWEARABLES_ENABLED", "").strip().lower()
    if not raw:
        return True
    return raw in _TRUE_VALUES


class OpenWearablesClient:
    """Tiny REST client for the Open Wearables API."""

    def __init__(self, config: OpenWearablesClientConfig):
        self.config = config

    @classmethod
    def from_env(cls) -> OpenWearablesClient:
        config = OpenWearablesClientConfig.from_env()
        if config is None or not openwearables_enabled():
            raise ValueError("Open Wearables is not configured.")
        return cls(config)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        headers = {"X-Open-Wearables-API-Key": self.config.api_key}
        url = f"{self.config.api_url}/api/v1{path}"
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            response = await client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
            )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    async def list_enabled_providers(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/oauth/providers", params={"enabled_only": "true"})
        providers = _coerce_items(data)
        result: list[dict[str, Any]] = []
        for provider in providers:
            result.append(
                {
                    "provider": str(provider.get("provider") or "").strip().lower(),
                    "name": str(provider.get("name") or provider.get("provider") or "").strip(),
                    "has_cloud_api": bool(provider.get("has_cloud_api", True)),
                    "is_enabled": bool(provider.get("is_enabled", True)),
                    "icon_url": str(provider.get("icon_url") or "").strip(),
                }
            )
        return [item for item in result if item["provider"]]

    async def find_user_by_external_id(self, external_user_id: str) -> dict[str, Any] | None:
        data = await self._request("GET", "/users", params={"search": external_user_id})
        for item in _coerce_items(data):
            if str(item.get("external_user_id") or "").strip() == external_user_id:
                return item
        return None

    async def create_user(
        self,
        *,
        external_user_id: str,
        email: str = "",
        display_name: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"external_user_id": external_user_id}
        if email:
            payload["email"] = email
        if display_name:
            parts = [part for part in display_name.split(" ") if part]
            if parts:
                payload["first_name"] = parts[0]
            if len(parts) > 1:
                payload["last_name"] = " ".join(parts[1:])
        return await self._request("POST", "/users", json_body=payload)

    async def get_or_create_user(
        self,
        *,
        external_user_id: str,
        email: str = "",
        display_name: str = "",
    ) -> dict[str, Any]:
        existing = await self.find_user_by_external_id(external_user_id)
        if existing is not None:
            return existing
        return await self.create_user(
            external_user_id=external_user_id,
            email=email,
            display_name=display_name,
        )

    async def authorize_provider(
        self,
        *,
        provider: str,
        user_id: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        query = urlencode({"user_id": user_id, "redirect_uri": redirect_uri})
        return await self._request("GET", f"/oauth/{provider}/authorize?{query}")

    async def list_connections(self, user_id: str) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/users/{user_id}/connections")
        connections = _coerce_items(data)
        result: list[dict[str, Any]] = []
        for item in connections:
            provider = str(item.get("provider") or "").strip().lower()
            if not provider:
                continue
            result.append(
                {
                    "provider": provider,
                    "status": str(item.get("status") or "").strip().lower() or "unknown",
                    "last_synced_at": str(item.get("last_synced_at") or "").strip(),
                    "updated_at": str(item.get("updated_at") or "").strip(),
                }
            )
        return result

    async def sync_provider(self, *, provider: str, user_id: str) -> dict[str, Any]:
        return await self._request("POST", f"/providers/{provider}/users/{user_id}/sync")

    async def _maybe_get(self, path: str, *, params: dict[str, Any]) -> Any:
        try:
            return await self._request("GET", path, params=params)
        except Exception:
            return {}

    async def fetch_snapshot(
        self,
        *,
        user_id: str,
        connections: list[dict[str, Any]] | None = None,
    ) -> WearableSnapshot:
        today = date.today()
        start_date = (today - timedelta(days=max(1, self.config.sync_window_days - 1))).isoformat()
        end_date = today.isoformat()
        start_time = f"{start_date}T00:00:00Z"
        end_time = f"{end_date}T23:59:59Z"

        if connections is None:
            connections = await self.list_connections(user_id)
        active_connections = [
            item for item in connections if str(item.get("status") or "") == "active"
        ]
        connected_providers = sorted({str(item.get("provider") or "") for item in active_connections if item.get("provider")})
        last_sync_at = max(
            (str(item.get("last_synced_at") or "") for item in active_connections),
            default="",
        )
        sleep_payload = await self._maybe_get(
            f"/users/{user_id}/summaries/sleep",
            params={"start_date": start_date, "end_date": end_date},
        )
        activity_payload = await self._maybe_get(
            f"/users/{user_id}/summaries/activity",
            params={"start_date": start_date, "end_date": end_date},
        )
        recovery_payload = await self._maybe_get(
            f"/users/{user_id}/summaries/recovery",
            params={"start_date": start_date, "end_date": end_date},
        )
        body_payload = await self._maybe_get(
            f"/users/{user_id}/summaries/body",
            params={"start_date": start_date, "end_date": end_date},
        )
        score_payload = await self._maybe_get(
            f"/users/{user_id}/health-scores",
            params={"start_date": start_date, "end_date": end_date},
        )

        summaries = {
            "sleep": _compact_summary("sleep", sleep_payload),
            "activity": _compact_summary("activity", activity_payload),
            "recovery": _compact_summary("recovery", recovery_payload),
            "body": _compact_summary("body", body_payload),
        }
        trend_flags = [
            flag
            for flag in (
                _summary_delta("sleep", _coerce_items(sleep_payload)),
                _summary_delta("activity", _coerce_items(activity_payload)),
                _summary_delta("recovery", _coerce_items(recovery_payload)),
            )
            if flag
        ]
        notes: list[str] = []
        if not connected_providers:
            notes.append("no active wearable providers connected yet")
        for name, summary in summaries.items():
            if not summary:
                notes.append(f"{name} summary unavailable")

        freshness = "unknown"
        freshness_note = "wearable data has not synced yet"
        parsed_sync = _parse_dt(last_sync_at)
        if parsed_sync is not None:
            age = datetime.now(UTC) - parsed_sync
            if age <= timedelta(hours=self.config.stale_after_hours):
                freshness = "fresh"
            else:
                freshness = "stale"
            freshness_note = f"{freshness} ({int(age.total_seconds() // 3600)}h since last sync)"

        timeseries_payload = await self._maybe_get(
            f"/users/{user_id}/timeseries",
            params={
                "start_time": start_time,
                "end_time": end_time,
                "types": ["heart_rate", "steps"],
            },
        )
        if summaries.get("activity") and not summaries["activity"].get("steps"):
            latest_ts = _pick_latest(_coerce_items(timeseries_payload))
            steps_value = _find_number(latest_ts, "steps", "value")
            if steps_value is not None:
                summaries["activity"]["steps"] = steps_value

        return WearableSnapshot(
            generated_at=_iso_now(),
            connected_providers=connected_providers,
            last_sync_at=last_sync_at,
            freshness=freshness,
            freshness_note=freshness_note,
            summaries={key: value for key, value in summaries.items() if value},
            health_scores=_compact_health_scores(score_payload),
            trend_flags=trend_flags,
            notes=notes,
        )


def _wearables_seed_from_workspace(
    health: HealthWorkspace,
    *,
    secret: str | None = None,
) -> dict[str, Any]:
    identity = health.load_openwearables_identity(secret=secret)
    setup = health.load_setup() or {}
    wearables = dict(setup.get("wearables") or {})
    cache = health.load_wearables_cache(secret=secret) or {}
    profile = health.load_profile() or {}
    preferences = dict(profile.get("wearables") or {})
    return {
        "enabled": bool(wearables.get("enabled") or preferences.get("enabled")),
        "preferred_providers": list(
            preferences.get("preferred_providers")
            or wearables.get("requested_providers")
            or wearables.get("connected_providers")
            or []
        ),
        "use_for_coaching": bool(preferences.get("use_for_coaching", False)),
        "connected_providers": list(wearables.get("connected_providers") or []),
        "openwearables_user_id": str(identity.get("openwearables_user_id") or ""),
        "external_user_id": str(identity.get("external_user_id") or ""),
        "snapshot": cache,
    }


async def ensure_openwearables_user(
    health: HealthWorkspace,
    *,
    external_user_id: str,
    email: str = "",
    display_name: str = "",
    secret: str | None = None,
) -> dict[str, Any]:
    client = OpenWearablesClient.from_env()
    user = await client.get_or_create_user(
        external_user_id=external_user_id,
        email=email,
        display_name=display_name,
    )
    health.store_openwearables_identity(
        openwearables_user_id=str(user.get("id") or ""),
        external_user_id=external_user_id,
        secret=secret,
    )
    return user


async def refresh_wearables_connections(
    health: HealthWorkspace,
    *,
    secret: str | None = None,
) -> dict[str, Any]:
    client = OpenWearablesClient.from_env()
    providers = await client.list_enabled_providers()
    identity = health.load_openwearables_identity(secret=secret)
    user_id = str(identity.get("openwearables_user_id") or "").strip()
    if not user_id:
        health.store_wearables_setup_state(
            available_providers=providers,
            last_error="Wearable user is not linked yet.",
        )
        return health.load_setup().get("wearables", {})
    connections = await client.list_connections(user_id)
    health.store_wearables_setup_state(
        available_providers=providers,
        connections=connections,
        last_error="",
    )
    return health.load_setup().get("wearables", {})


async def start_wearable_authorization(
    health: HealthWorkspace,
    *,
    provider: str,
    external_user_id: str,
    redirect_uri: str,
    email: str = "",
    display_name: str = "",
    secret: str | None = None,
) -> dict[str, Any]:
    client = OpenWearablesClient.from_env()
    providers = await client.list_enabled_providers()
    normalized_provider = str(provider or "").strip().lower()
    enabled_names = {item["provider"] for item in providers if item.get("is_enabled")}
    if normalized_provider not in enabled_names:
        raise ValueError("Selected wearable provider is not enabled in Open Wearables.")
    user = await ensure_openwearables_user(
        health,
        external_user_id=external_user_id,
        email=email,
        display_name=display_name,
        secret=secret,
    )
    authorization = await client.authorize_provider(
        provider=normalized_provider,
        user_id=str(user.get("id") or ""),
        redirect_uri=redirect_uri,
    )
    requested = sorted({normalized_provider, *list((health.load_setup() or {}).get("wearables", {}).get("requested_providers", []))})
    health.store_wearables_setup_state(
        enabled=True,
        available_providers=providers,
        requested_providers=requested,
        authorization={
            "provider": normalized_provider,
            "redirect_uri": redirect_uri,
            "started_at": _iso_now(),
            "state": str(authorization.get("state") or ""),
        },
        last_error="",
    )
    health.update_wearables_preferences(
        enabled=True,
        preferred_providers=requested,
        use_for_coaching=True,
    )
    return authorization


async def sync_wearable_snapshot(
    health: HealthWorkspace,
    *,
    provider: str | None = None,
    secret: str | None = None,
) -> WearableSnapshot:
    client = OpenWearablesClient.from_env()
    identity = health.load_openwearables_identity(secret=secret)
    user_id = str(identity.get("openwearables_user_id") or "").strip()
    if not user_id:
        raise ValueError("Wearable user is not linked yet.")
    connections = await client.list_connections(user_id)
    active_providers = [
        str(item.get("provider") or "").strip().lower()
        for item in connections
        if str(item.get("status") or "").strip().lower() == "active"
    ]
    if provider:
        targets = [str(provider).strip().lower()]
    else:
        targets = active_providers
    if not targets:
        raise ValueError("No active wearable connections are available to sync.")
    last_error = ""
    for target in targets:
        try:
            await client.sync_provider(provider=target, user_id=user_id)
        except Exception as exc:
            last_error = str(exc)
    refreshed_connections = await client.list_connections(user_id)
    snapshot = await client.fetch_snapshot(user_id=user_id, connections=refreshed_connections)
    health.save_wearables_cache(snapshot.to_dict(), secret=secret)
    health.store_wearables_setup_state(
        enabled=True,
        connections=refreshed_connections,
        last_sync_status="ok" if not last_error else "partial_error",
        last_sync_at=snapshot.last_sync_at or snapshot.generated_at,
        last_error=last_error,
    )
    health.record_wearables_runtime(
        snapshot=snapshot.to_dict(),
        status="ok" if not last_error else "partial_error",
    )
    health.update_wearables_preferences(
        enabled=True,
        preferred_providers=sorted(set(active_providers or targets)),
        use_for_coaching=True,
    )
    return snapshot


def wearable_context_lines(
    health: HealthWorkspace,
    *,
    secret: str | None = None,
) -> list[str]:
    snapshot = WearableSnapshot.from_dict(health.load_wearables_cache(secret=secret) or {})
    if snapshot is None:
        return []
    return snapshot.context_lines()


def wearable_seed_payload(
    health: HealthWorkspace,
    *,
    secret: str | None = None,
) -> dict[str, Any]:
    return _wearables_seed_from_workspace(health, secret=secret)
