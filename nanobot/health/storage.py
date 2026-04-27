"""Storage helpers for health-enabled workspaces."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken

from nanobot.utils.helpers import ensure_dir

_PROFILE_NAME = "profile.json"
_VAULT_NAME = "vault.json.enc"
_INVITES_NAME = "invites.json"
_SETUP_NAME = "setup.json"
_SETUP_SECRETS_NAME = "setup-secrets.json.enc"
_RUNTIME_NAME = "runtime.json"
_WEARABLES_CACHE_NAME = "wearables-cache.json.enc"
_DEFAULT_INVITE_TTL_HOURS = 24
_DEFAULT_SETUP_TTL_HOURS = 24 * 7
_DEFAULT_HOSTED_PROVIDER = "minimax"
_DEFAULT_HOSTED_MODEL = "MiniMax-M2.7"
_PREFERRED_NAME_MAX_LEN = 40
_CLOCK_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _clean_list(values: list[str] | None) -> list[str]:
    return [value.strip() for value in values or [] if value and value.strip()]


def derive_preferred_name(full_name: str) -> str:
    cleaned = " ".join(str(full_name or "").strip().split())
    if not cleaned:
        return ""

    honorifics = {
        "mr",
        "mrs",
        "ms",
        "miss",
        "dr",
        "prof",
        "sir",
        "madam",
        "coach",
    }
    tokens = [part for part in cleaned.split(" ") if part]
    while tokens and tokens[0].rstrip(".").lower() in honorifics:
        tokens.pop(0)
    candidate = (tokens[0] if tokens else cleaned).strip(",.;:!?")
    return candidate[:_PREFERRED_NAME_MAX_LEN]


def normalize_preferred_name(value: str) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    return cleaned[:_PREFERRED_NAME_MAX_LEN]


def validate_health_timezone(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError("Timezone cannot be empty.")
    try:
        ZoneInfo(cleaned)
    except Exception as exc:
        raise ValueError(f"Unknown timezone '{cleaned}'. Use a valid IANA timezone like 'Asia/Colombo'.") from exc
    return cleaned


def normalize_clock_time(value: str | None, *, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if not _CLOCK_RE.match(cleaned):
        raise ValueError(f"{field_name} must use 24-hour HH:MM format.")
    return cleaned


def normalize_optional_bool(value: bool | None) -> bool | None:
    """Normalize optional boolean flags without coercing absent values."""
    if value is None:
        return None
    return bool(value)


def _default_setup_payload(token: str, *, ttl_hours: int) -> dict[str, Any]:
    now = _utcnow()
    return {
        "token": token,
        "created_at": _isoformat(now),
        "expires_at": _isoformat(now + timedelta(hours=ttl_hours)),
        "completed_at": None,
        "state": "draft",
        "provider": {
            "provider": _DEFAULT_HOSTED_PROVIDER,
            "model": _DEFAULT_HOSTED_MODEL,
            "validated_at": None,
            "api_key_masked": "",
        },
        "channels": {
            "telegram": {
                "connected": False,
                "validated_at": None,
                "bot_id": None,
                "bot_username": "",
                "bot_url": "",
            },
            "whatsapp": {
                "connected": False,
                "status": "waiting",
                "connected_at": None,
                "jid": "",
                "phone": "",
                "chat_url": "",
            },
        },
        "profile": {
            "submitted_at": None,
            "phase1": {},
            "phase2": {},
        },
        "wearables": {
            "enabled": False,
            "available_providers": [],
            "requested_providers": [],
            "connected_providers": [],
            "authorization": {
                "provider": "",
                "state": "",
                "redirect_uri": "",
                "started_at": None,
            },
            "last_sync_at": "",
            "last_sync_status": "idle",
            "last_error": "",
            "user_linked_at": None,
        },
    }


def _default_runtime_payload() -> dict[str, Any]:
    return {
        "last_user_message_at": "",
        "last_user_local_date": "",
        "last_morning_checkin_sent_local_date": "",
        "last_weekly_summary_sent_iso_week": "",
        "last_proactive_delivery_at": "",
        "last_proactive_source": "",
        "wearables": {
            "last_sync_at": "",
            "last_sync_status": "idle",
            "snapshot_updated_at": "",
            "freshness": "",
            "connected_providers": [],
        },
    }


def _mask_secret(value: str, *, keep: int = 4) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) <= keep:
        return "*" * len(raw)
    return "*" * max(0, len(raw) - keep) + raw[-keep:]


def _compute_setup_state(setup: dict[str, Any]) -> str:
    if setup.get("completed_at"):
        return "active"
    provider_ready = bool(setup.get("provider", {}).get("validated_at"))
    channels = setup.get("channels", {})
    channel_ready = any(
        bool(channel.get("connected"))
        for channel in channels.values()
        if isinstance(channel, dict)
    )
    profile_ready = bool(setup.get("profile", {}).get("submitted_at"))
    if provider_ready and channel_ready and profile_ready:
        return "profile_ready"
    if provider_ready and channel_ready:
        return "channels_ready"
    if provider_ready:
        return "provider_ready"
    return "draft"


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _coerce_local_now(
    *,
    timezone: str,
    now: datetime | None = None,
) -> datetime:
    base = now or _utcnow()
    if base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    return base.astimezone(tz)


def _local_date_string(*, timezone: str, now: datetime | None = None) -> str:
    return _coerce_local_now(timezone=timezone, now=now).strftime("%Y-%m-%d")


def _iso_week_string(*, timezone: str, now: datetime | None = None) -> str:
    local_now = _coerce_local_now(timezone=timezone, now=now)
    iso_year, iso_week, _ = local_now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_health_vault_secret() -> str:
    secret = os.environ.get("HEALTH_VAULT_KEY", "").strip()
    if not secret:
        raise ValueError("HEALTH_VAULT_KEY is required for health-enabled workspaces.")
    return secret


def encrypt_json(payload: dict[str, Any], *, secret: str | None = None) -> str:
    fernet = Fernet(_derive_fernet_key(secret or get_health_vault_secret()))
    return fernet.encrypt(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).decode("utf-8")


def decrypt_json(ciphertext: str, *, secret: str | None = None) -> dict[str, Any]:
    fernet = Fernet(_derive_fernet_key(secret or get_health_vault_secret()))
    try:
        decrypted = fernet.decrypt(ciphertext.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt health vault with the configured key.") from exc
    return json.loads(decrypted.decode("utf-8"))


def get_onboarding_base_url() -> str:
    base = (
        os.environ.get("HEALTH_ONBOARDING_BASE_URL")
        or os.environ.get("NANOBOT_PUBLIC_BASE_URL")
        or "http://localhost:8080"
    ).strip()
    return base.rstrip("/")


def health_distribution_enabled(workspace: Path | None = None) -> bool:
    flag = os.environ.get("NANOBOT_HEALTH_MODE", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if workspace is None:
        return False
    health_dir = workspace / "health"
    return any(
        path.exists()
        for path in (
            health_dir,
            health_dir / _PROFILE_NAME,
            health_dir / _INVITES_NAME,
            health_dir / _SETUP_NAME,
        )
    )


class HealthWorkspace:
    """File-backed health state for a single nanobot workspace."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.health_dir = ensure_dir(workspace / "health")
        self.profile_path = self.health_dir / _PROFILE_NAME
        self.vault_path = self.health_dir / _VAULT_NAME
        self.invites_path = self.health_dir / _INVITES_NAME
        self.setup_path = self.health_dir / _SETUP_NAME
        self.setup_secrets_path = self.health_dir / _SETUP_SECRETS_NAME
        self.runtime_path = self.health_dir / _RUNTIME_NAME
        self.wearables_cache_path = self.health_dir / _WEARABLES_CACHE_NAME

    @property
    def enabled(self) -> bool:
        return self.profile_path.exists()

    def load_profile(self) -> dict[str, Any] | None:
        if not self.profile_path.exists():
            return None
        return json.loads(self.profile_path.read_text(encoding="utf-8"))

    def save_profile(self, profile: dict[str, Any]) -> None:
        ensure_dir(self.health_dir)
        self.profile_path.write_text(
            json.dumps(profile, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def load_runtime(self) -> dict[str, Any]:
        if not self.runtime_path.exists():
            return _default_runtime_payload()
        try:
            raw = json.loads(self.runtime_path.read_text(encoding="utf-8"))
        except Exception:
            return _default_runtime_payload()
        if not isinstance(raw, dict):
            return _default_runtime_payload()
        return _merge_dict(_default_runtime_payload(), raw)

    def save_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        ensure_dir(self.health_dir)
        normalized = _merge_dict(_default_runtime_payload(), payload)
        self.runtime_path.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return normalized

    def load_wearables_cache(self, *, secret: str | None = None) -> dict[str, Any] | None:
        if not self.wearables_cache_path.exists():
            return None
        ciphertext = self.wearables_cache_path.read_text(encoding="utf-8").strip()
        if not ciphertext:
            return None
        return decrypt_json(ciphertext, secret=secret)

    def save_wearables_cache(self, payload: dict[str, Any], *, secret: str | None = None) -> None:
        ensure_dir(self.health_dir)
        encrypted = encrypt_json(payload, secret=secret)
        self.wearables_cache_path.write_text(encrypted + "\n", encoding="utf-8")

    def refresh_workspace_assets(self, *, include_memory: bool = False) -> None:
        profile = self.load_profile()
        if not profile:
            return
        from nanobot.health.bootstrap import refresh_health_workspace_assets

        refresh_health_workspace_assets(
            self.workspace,
            profile,
            include_memory=include_memory,
        )

    def record_user_activity(
        self,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        profile = self.load_profile() or {}
        timezone = str(profile.get("timezone") or "UTC").strip() or "UTC"
        runtime = self.load_runtime()
        current = (now or _utcnow()).astimezone(UTC)
        runtime["last_user_message_at"] = _isoformat(current)
        runtime["last_user_local_date"] = _local_date_string(timezone=timezone, now=current)
        return self.save_runtime(runtime)

    def record_proactive_delivery(
        self,
        *,
        source: str,
        now: datetime | None = None,
        morning_checkin_sent: bool = False,
        weekly_summary_sent: bool = False,
    ) -> dict[str, Any]:
        profile = self.load_profile() or {}
        timezone = str(profile.get("timezone") or "UTC").strip() or "UTC"
        current = (now or _utcnow()).astimezone(UTC)
        runtime = self.load_runtime()
        runtime["last_proactive_delivery_at"] = _isoformat(current)
        runtime["last_proactive_source"] = str(source or "").strip()
        if morning_checkin_sent:
            runtime["last_morning_checkin_sent_local_date"] = _local_date_string(
                timezone=timezone,
                now=current,
            )
        if weekly_summary_sent:
            runtime["last_weekly_summary_sent_iso_week"] = _iso_week_string(
                timezone=timezone,
                now=current,
            )
        return self.save_runtime(runtime)

    def load_vault(self, *, secret: str | None = None) -> dict[str, Any] | None:
        if not self.vault_path.exists():
            return None
        ciphertext = self.vault_path.read_text(encoding="utf-8").strip()
        if not ciphertext:
            return None
        return decrypt_json(ciphertext, secret=secret)

    def save_vault(self, vault: dict[str, Any], *, secret: str | None = None) -> None:
        ensure_dir(self.health_dir)
        encrypted = encrypt_json(vault, secret=secret)
        self.vault_path.write_text(encrypted + "\n", encoding="utf-8")

    def load_preferred_name(self, *, secret: str | None = None) -> str:
        vault = self.load_vault(secret=secret) or {}
        contact = vault.get("contact") or {}
        preferred = normalize_preferred_name(contact.get("preferred_name", ""))
        if preferred:
            return preferred
        return derive_preferred_name(contact.get("full_name", ""))

    def save_preferred_name(self, preferred_name: str, *, secret: str | None = None) -> str:
        cleaned = normalize_preferred_name(preferred_name)
        if not cleaned:
            raise ValueError("Preferred name cannot be empty.")

        vault = self.load_vault(secret=secret) or {}
        contact = vault.setdefault("contact", {})
        identifiers = vault.setdefault("identifiers", {})
        person_names = _clean_list(identifiers.get("person_names"))

        if cleaned.lower() not in {value.lower() for value in person_names}:
            person_names.append(cleaned)
            identifiers["person_names"] = person_names

        contact["preferred_name"] = cleaned
        self.save_vault(vault, secret=secret)
        return cleaned

    def update_profile(
        self,
        *,
        timezone: str | None = None,
        location: str | None = None,
        wake_time: str | None = None,
        sleep_time: str | None = None,
        preferred_name: str | None = None,
        preferred_channel: str | None = None,
        proactive_enabled: bool | None = None,
        voice_preferred: bool | None = None,
        last_seen_local_date: str | None = None,
        wearables_enabled: bool | None = None,
        wearable_preferred_providers: list[str] | None = None,
        wearables_use_for_coaching: bool | None = None,
        secret: str | None = None,
    ) -> dict[str, Any]:
        profile = self.load_profile()
        if not profile:
            raise ValueError("Health profile not found.")

        changed: dict[str, Any] = {}

        if timezone is not None:
            cleaned = validate_health_timezone(timezone)
            profile["timezone"] = cleaned
            changed["timezone"] = cleaned

        if location is not None:
            cleaned = " ".join(str(location).strip().split())
            profile["location"] = cleaned
            changed["location"] = cleaned
            vault = self.load_vault(secret=secret) or {}
            contact = vault.setdefault("contact", {})
            contact["location"] = cleaned
            self.save_vault(vault, secret=secret)

        routines = profile.setdefault("routines", {})
        if wake_time is not None:
            cleaned = normalize_clock_time(wake_time, field_name="wake_time")
            routines["wake_time"] = cleaned
            changed["wake_time"] = cleaned
        if sleep_time is not None:
            cleaned = normalize_clock_time(sleep_time, field_name="sleep_time")
            routines["sleep_time"] = cleaned
            changed["sleep_time"] = cleaned

        if preferred_channel is not None:
            cleaned = str(preferred_channel or "").strip().lower()
            if cleaned not in {"telegram", "whatsapp"}:
                raise ValueError("preferred_channel must be either 'telegram' or 'whatsapp'.")
            profile["preferred_channel"] = cleaned
            profile.setdefault("channel_binding", {})["preferred_channel"] = cleaned
            changed["preferred_channel"] = cleaned

        if preferred_name is not None:
            cleaned = self.save_preferred_name(preferred_name, secret=secret)
            changed["preferred_name"] = cleaned

        if proactive_enabled is not None:
            cleaned = normalize_optional_bool(proactive_enabled)
            profile["proactive_enabled"] = cleaned
            changed["proactive_enabled"] = cleaned

        if voice_preferred is not None:
            cleaned = normalize_optional_bool(voice_preferred)
            profile["voice_preferred"] = cleaned
            changed["voice_preferred"] = cleaned

        if last_seen_local_date is not None:
            cleaned = " ".join(str(last_seen_local_date or "").strip().split())
            if cleaned and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
                raise ValueError("last_seen_local_date must use YYYY-MM-DD format.")
            profile["last_seen_local_date"] = cleaned
            changed["last_seen_local_date"] = cleaned

        wearables = profile.setdefault("wearables", {})
        if wearables_enabled is not None:
            cleaned = normalize_optional_bool(wearables_enabled)
            wearables["enabled"] = cleaned
            changed["wearables_enabled"] = cleaned
        if wearable_preferred_providers is not None:
            cleaned = sorted(
                {
                    str(item or "").strip().lower()
                    for item in wearable_preferred_providers
                    if str(item or "").strip()
                }
            )
            wearables["preferred_providers"] = cleaned
            changed["wearable_preferred_providers"] = cleaned
        if wearables_use_for_coaching is not None:
            cleaned = normalize_optional_bool(wearables_use_for_coaching)
            wearables["use_for_coaching"] = cleaned
            changed["wearables_use_for_coaching"] = cleaned

        self.save_profile(profile)
        if changed:
            self.refresh_workspace_assets(include_memory=False)
        return changed

    def load_setup(self) -> dict[str, Any] | None:
        if not self.setup_path.exists():
            return None
        raw = json.loads(self.setup_path.read_text(encoding="utf-8"))
        token = raw.get("token") or secrets.token_urlsafe(18).replace("_", "").replace("-", "")[:24]
        setup = _merge_dict(_default_setup_payload(token, ttl_hours=_DEFAULT_SETUP_TTL_HOURS), raw)
        setup["state"] = _compute_setup_state(setup)
        return setup

    def save_setup(self, setup: dict[str, Any]) -> None:
        ensure_dir(self.health_dir)
        normalized = _merge_dict(
            _default_setup_payload(
                setup.get("token") or secrets.token_urlsafe(18).replace("_", "").replace("-", "")[:24],
                ttl_hours=_DEFAULT_SETUP_TTL_HOURS,
            ),
            setup,
        )
        normalized["state"] = _compute_setup_state(normalized)
        self.setup_path.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def store_wearables_setup_state(
        self,
        *,
        enabled: bool | None = None,
        available_providers: list[dict[str, Any]] | None = None,
        requested_providers: list[str] | None = None,
        connections: list[dict[str, Any]] | None = None,
        authorization: dict[str, Any] | None = None,
        last_sync_at: str | None = None,
        last_sync_status: str | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any]:
        setup = self.load_setup() or {}
        wearables = setup.setdefault("wearables", {})
        if enabled is not None:
            wearables["enabled"] = bool(enabled)
        if available_providers is not None:
            wearables["available_providers"] = available_providers
        if requested_providers is not None:
            wearables["requested_providers"] = sorted(
                {
                    str(item or "").strip().lower()
                    for item in requested_providers
                    if str(item or "").strip()
                }
            )
        if connections is not None:
            connected = [
                str(item.get("provider") or "").strip().lower()
                for item in connections
                if str(item.get("status") or "").strip().lower() == "active"
            ]
            wearables["connected_providers"] = sorted({item for item in connected if item})
            if wearables["connected_providers"] and not wearables.get("user_linked_at"):
                wearables["user_linked_at"] = _isoformat(_utcnow())
        if authorization is not None:
            wearables["authorization"] = _merge_dict(
                {
                    "provider": "",
                    "state": "",
                    "redirect_uri": "",
                    "started_at": None,
                },
                authorization,
            )
        if last_sync_at is not None:
            wearables["last_sync_at"] = str(last_sync_at or "").strip()
        if last_sync_status is not None:
            wearables["last_sync_status"] = str(last_sync_status or "").strip() or "idle"
        if last_error is not None:
            wearables["last_error"] = str(last_error or "").strip()
        self.save_setup(setup)
        return setup

    def update_wearables_preferences(
        self,
        *,
        enabled: bool | None = None,
        preferred_providers: list[str] | None = None,
        use_for_coaching: bool | None = None,
    ) -> dict[str, Any]:
        profile = self.load_profile() or {}
        wearables = profile.setdefault("wearables", {})
        if enabled is not None:
            wearables["enabled"] = bool(enabled)
        if preferred_providers is not None:
            wearables["preferred_providers"] = sorted(
                {
                    str(item or "").strip().lower()
                    for item in preferred_providers
                    if str(item or "").strip()
                }
            )
        if use_for_coaching is not None:
            wearables["use_for_coaching"] = bool(use_for_coaching)
        if profile:
            self.save_profile(profile)
        return profile

    def load_setup_secrets(self, *, secret: str | None = None) -> dict[str, Any]:
        if not self.setup_secrets_path.exists():
            return {}
        ciphertext = self.setup_secrets_path.read_text(encoding="utf-8").strip()
        if not ciphertext:
            return {}
        return decrypt_json(ciphertext, secret=secret)

    def save_setup_secrets(self, payload: dict[str, Any], *, secret: str | None = None) -> None:
        ensure_dir(self.health_dir)
        encrypted = encrypt_json(payload, secret=secret)
        self.setup_secrets_path.write_text(encrypted + "\n", encoding="utf-8")

    def load_openwearables_identity(self, *, secret: str | None = None) -> dict[str, Any]:
        payload = self.load_setup_secrets(secret=secret)
        wearables = payload.get("wearables") or {}
        return {
            "openwearables_user_id": str(wearables.get("openwearables_user_id") or "").strip(),
            "external_user_id": str(wearables.get("external_user_id") or "").strip(),
        }

    def store_openwearables_identity(
        self,
        *,
        openwearables_user_id: str,
        external_user_id: str,
        secret: str | None = None,
    ) -> dict[str, Any]:
        payload = self.load_setup_secrets(secret=secret)
        wearables = payload.setdefault("wearables", {})
        wearables["openwearables_user_id"] = str(openwearables_user_id or "").strip()
        wearables["external_user_id"] = str(external_user_id or "").strip()
        self.save_setup_secrets(payload, secret=secret)
        self.store_wearables_setup_state(enabled=True)
        return wearables

    def record_wearables_runtime(
        self,
        *,
        snapshot: dict[str, Any],
        status: str,
    ) -> dict[str, Any]:
        runtime = self.load_runtime()
        wearables = runtime.setdefault("wearables", {})
        wearables["last_sync_at"] = str(snapshot.get("last_sync_at") or snapshot.get("generated_at") or "").strip()
        wearables["snapshot_updated_at"] = str(snapshot.get("generated_at") or "").strip()
        wearables["freshness"] = str(snapshot.get("freshness") or "").strip()
        wearables["connected_providers"] = list(snapshot.get("connected_providers") or [])
        wearables["last_sync_status"] = str(status or "").strip() or "idle"
        return self.save_runtime(runtime)

    def load_invites(self) -> dict[str, dict[str, Any]]:
        if not self.invites_path.exists():
            return {}
        raw = json.loads(self.invites_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def save_invites(self, invites: dict[str, dict[str, Any]]) -> None:
        ensure_dir(self.health_dir)
        self.invites_path.write_text(
            json.dumps(invites, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def create_invite(
        self,
        *,
        channel: str,
        chat_id: str,
        ttl_hours: int = _DEFAULT_INVITE_TTL_HOURS,
    ) -> tuple[str, dict[str, Any]]:
        invites = self.load_invites()
        token = secrets.token_urlsafe(18).replace("_", "").replace("-", "")[:24]
        now = _utcnow()
        invite = {
            "channel": channel,
            "chat_id": chat_id,
            "created_at": _isoformat(now),
            "expires_at": _isoformat(now + timedelta(hours=ttl_hours)),
            "used_at": None,
        }
        invites[token] = invite
        self.save_invites(invites)
        return token, invite

    def get_invite(self, token: str) -> dict[str, Any] | None:
        return self.load_invites().get(token)

    def validate_invite(self, token: str) -> dict[str, Any] | None:
        invite = self.get_invite(token)
        if not invite:
            return None
        if invite.get("used_at"):
            return None
        expires_at = _parse_timestamp(invite.get("expires_at"))
        if expires_at and expires_at < _utcnow():
            return None
        return invite

    def consume_invite(self, token: str) -> None:
        invites = self.load_invites()
        invite = invites.get(token)
        if not invite:
            return
        invite["used_at"] = _isoformat(_utcnow())
        invites[token] = invite
        self.save_invites(invites)

    def onboarding_url(self, token: str) -> str:
        return f"{get_onboarding_base_url()}/onboard/{token}"

    def find_active_invite(self, *, channel: str, chat_id: str) -> tuple[str, dict[str, Any]] | None:
        for token, invite in self.load_invites().items():
            if invite.get("channel") != channel or invite.get("chat_id") != chat_id:
                continue
            if invite.get("used_at"):
                continue
            expires_at = _parse_timestamp(invite.get("expires_at"))
            if expires_at and expires_at < _utcnow():
                continue
            return token, invite
        return None

    def get_or_create_invite(
        self,
        *,
        channel: str,
        chat_id: str,
        ttl_hours: int = _DEFAULT_INVITE_TTL_HOURS,
    ) -> tuple[str, dict[str, Any]]:
        existing = self.find_active_invite(channel=channel, chat_id=chat_id)
        if existing is not None:
            return existing
        return self.create_invite(channel=channel, chat_id=chat_id, ttl_hours=ttl_hours)

    def create_setup_session(
        self,
        *,
        ttl_hours: int = _DEFAULT_SETUP_TTL_HOURS,
    ) -> tuple[str, dict[str, Any]]:
        token = secrets.token_urlsafe(18).replace("_", "").replace("-", "")[:24]
        setup = _default_setup_payload(token, ttl_hours=ttl_hours)
        self.save_setup(setup)
        return token, setup

    def create_setup_session_with_token(
        self,
        token: str,
        *,
        ttl_hours: int = _DEFAULT_SETUP_TTL_HOURS,
    ) -> tuple[str, dict[str, Any]]:
        cleaned = (token or "").strip()
        if not cleaned:
            raise ValueError("Setup token cannot be empty.")
        setup = _default_setup_payload(cleaned, ttl_hours=ttl_hours)
        self.save_setup(setup)
        return cleaned, setup

    def validate_setup_token(self, token: str) -> dict[str, Any] | None:
        setup = self.load_setup()
        if not setup or setup.get("token") != token:
            return None
        expires_at = _parse_timestamp(setup.get("expires_at"))
        if expires_at and expires_at < _utcnow():
            return None
        return setup

    def get_or_create_setup_session(
        self,
        *,
        ttl_hours: int = _DEFAULT_SETUP_TTL_HOURS,
    ) -> tuple[str, dict[str, Any]]:
        setup = self.load_setup()
        if setup and self.validate_setup_token(setup.get("token", "")):
            return setup["token"], setup
        return self.create_setup_session(ttl_hours=ttl_hours)

    def has_setup_session(self) -> bool:
        setup = self.load_setup()
        if not setup:
            return False
        return self.validate_setup_token(setup.get("token", "")) is not None

    def mark_setup_active(self) -> dict[str, Any]:
        setup = self.load_setup() or {}
        setup["completed_at"] = _isoformat(_utcnow())
        setup["state"] = "active"
        self.save_setup(setup)
        return setup

    def setup_expired(self) -> bool:
        setup = self.load_setup()
        if not setup:
            return False
        expires_at = _parse_timestamp(setup.get("expires_at"))
        if expires_at is None:
            return False
        return expires_at < _utcnow()

    def setup_url(self, token: str) -> str:
        return f"{get_onboarding_base_url()}/setup/{token}"

    def connected_channels(self) -> dict[str, dict[str, Any]]:
        setup = self.load_setup() or {}
        channels = setup.get("channels", {})
        return {
            name: info
            for name, info in channels.items()
            if isinstance(info, dict) and info.get("connected")
        }

    def runtime_overrides(self, *, secret: str | None = None) -> dict[str, Any] | None:
        setup = self.load_setup()
        if not setup or setup.get("state") != "active":
            return None
        try:
            secrets_payload = self.load_setup_secrets(secret=secret)
        except Exception:
            return None
        provider_key = secrets_payload.get("provider", {}).get("api_key", "").strip()
        telegram_token = secrets_payload.get("telegram", {}).get("bot_token", "").strip()
        whatsapp_bridge_url = (
            os.environ.get("NANOBOT_WHATSAPP_BRIDGE_URL")
            or os.environ.get("HEALTH_WHATSAPP_BRIDGE_URL")
            or "ws://whatsapp-bridge:3001"
        ).strip()
        whatsapp_bridge_token = (
            os.environ.get("WHATSAPP_BRIDGE_TOKEN")
            or os.environ.get("BRIDGE_TOKEN")
            or ""
        ).strip()
        channels = setup.get("channels", {})
        return {
            "provider": {
                "provider": setup.get("provider", {}).get("provider") or _DEFAULT_HOSTED_PROVIDER,
                "model": setup.get("provider", {}).get("model") or _DEFAULT_HOSTED_MODEL,
                "api_key": provider_key,
            },
            "channels": {
                "telegram": {
                    "enabled": bool(channels.get("telegram", {}).get("connected") and telegram_token),
                    "token": telegram_token,
                    "allow_from": ["*"],
                },
                "whatsapp": {
                    "enabled": bool(channels.get("whatsapp", {}).get("connected")),
                    "allow_from": ["*"],
                    "bridge_url": whatsapp_bridge_url,
                    "bridge_token": whatsapp_bridge_token,
                },
            },
        }

    def bind_chat_session(self, *, channel: str, chat_id: str, secret: str | None = None) -> None:
        profile = self.load_profile()
        if not profile:
            return
        changed = False
        binding = profile.setdefault("channel_binding", {})
        bound_channels = set(_clean_list(binding.get("bound_channels")))
        if channel not in bound_channels:
            bound_channels.add(channel)
            binding["bound_channels"] = sorted(bound_channels)
            changed = True
        if binding.get("last_channel") != channel:
            binding["last_channel"] = channel
            changed = True
        if binding.get("last_chat_id") != chat_id:
            binding["last_chat_id"] = chat_id
            changed = True
        if changed:
            self.save_profile(profile)

        vault = self.load_vault(secret=secret) or {}
        identifiers = vault.setdefault("identifiers", {})
        chat_ids = set(_clean_list(identifiers.get("chat_ids")))
        channels = set(_clean_list(identifiers.get("channels")))
        if chat_id and chat_id not in chat_ids:
            chat_ids.add(chat_id)
            identifiers["chat_ids"] = sorted(chat_ids)
            changed = True
        if channel and channel not in channels:
            channels.add(channel)
            identifiers["channels"] = sorted(channels)
            changed = True
        contact = vault.setdefault("contact", {})
        if not contact.get("invite_channel") and channel:
            contact["invite_channel"] = channel
            changed = True
        if not contact.get("invite_chat_id") and chat_id:
            contact["invite_chat_id"] = chat_id
            changed = True
        if changed:
            self.save_vault(vault, secret=secret)

    def store_provider_secret(
        self,
        *,
        provider_name: str,
        model: str,
        api_key: str,
        secret: str | None = None,
    ) -> dict[str, Any]:
        secrets_payload = self.load_setup_secrets(secret=secret)
        provider = secrets_payload.setdefault("provider", {})
        provider["provider"] = provider_name.strip()
        provider["model"] = model.strip()
        provider["api_key"] = api_key.strip()
        self.save_setup_secrets(secrets_payload, secret=secret)
        setup = self.load_setup() or {}
        setup_provider = setup.setdefault("provider", {})
        setup_provider["provider"] = provider_name.strip() or _DEFAULT_HOSTED_PROVIDER
        setup_provider["model"] = model.strip() or _DEFAULT_HOSTED_MODEL
        setup_provider["api_key_masked"] = _mask_secret(api_key)
        setup_provider["validated_at"] = _isoformat(_utcnow())
        self.save_setup(setup)
        return setup

    def store_telegram_secret(
        self,
        *,
        bot_token: str,
        bot_id: int | None,
        bot_username: str,
        secret: str | None = None,
    ) -> dict[str, Any]:
        secrets_payload = self.load_setup_secrets(secret=secret)
        telegram = secrets_payload.setdefault("telegram", {})
        telegram["bot_token"] = bot_token.strip()
        self.save_setup_secrets(secrets_payload, secret=secret)
        setup = self.load_setup() or {}
        telegram_meta = setup.setdefault("channels", {}).setdefault("telegram", {})
        telegram_meta.update(
            {
                "connected": True,
                "validated_at": _isoformat(_utcnow()),
                "bot_id": bot_id,
                "bot_username": bot_username,
                "bot_url": f"https://t.me/{bot_username}" if bot_username else "",
            }
        )
        self.save_setup(setup)
        return setup

    def update_whatsapp_status(
        self,
        *,
        status: str,
        jid: str = "",
        phone: str = "",
        chat_url: str = "",
    ) -> dict[str, Any]:
        setup = self.load_setup() or {}
        whatsapp = setup.setdefault("channels", {}).setdefault("whatsapp", {})
        whatsapp["status"] = status
        if status == "connected":
            whatsapp["connected"] = True
            whatsapp["connected_at"] = whatsapp.get("connected_at") or _isoformat(_utcnow())
        else:
            whatsapp["connected"] = False
        if jid:
            whatsapp["jid"] = jid
        if phone:
            whatsapp["phone"] = phone
        if chat_url:
            whatsapp["chat_url"] = chat_url
        self.save_setup(setup)
        return setup

    def store_profile_draft(
        self,
        *,
        submission: dict[str, Any],
        secret: str | None = None,
    ) -> dict[str, Any]:
        phase1 = dict(submission.get("phase1") or {})
        identity = {
            "full_name": phase1.pop("full_name", "").strip(),
            "email": phase1.pop("email", "").strip(),
            "phone": phase1.pop("phone", "").strip(),
        }
        secrets_payload = self.load_setup_secrets(secret=secret)
        secrets_payload["profile_identity"] = identity
        self.save_setup_secrets(secrets_payload, secret=secret)

        setup = self.load_setup() or {}
        setup["profile"] = {
            "submitted_at": _isoformat(_utcnow()),
            "phase1": phase1,
            "phase2": submission.get("phase2") or {},
        }
        self.save_setup(setup)
        return setup

    def load_profile_draft_submission(self, *, secret: str | None = None) -> dict[str, Any] | None:
        setup = self.load_setup() or {}
        profile = setup.get("profile") or {}
        if not profile.get("submitted_at"):
            return None
        secrets_payload = self.load_setup_secrets(secret=secret)
        identity = secrets_payload.get("profile_identity") or {}
        phase1 = dict(profile.get("phase1") or {})
        phase1.update(
            {
                "full_name": identity.get("full_name", ""),
                "email": identity.get("email", ""),
                "phone": identity.get("phone", ""),
            }
        )
        return {
            "phase1": phase1,
            "phase2": dict(profile.get("phase2") or {}),
        }

    def apply_wearables_seed(self, seed: dict[str, Any], *, secret: str | None = None) -> None:
        if not isinstance(seed, dict):
            return
        preferred_providers = list(seed.get("preferred_providers") or seed.get("connected_providers") or [])
        self.update_wearables_preferences(
            enabled=bool(seed.get("enabled")),
            preferred_providers=preferred_providers,
            use_for_coaching=bool(seed.get("use_for_coaching", False)),
        )
        user_id = str(seed.get("openwearables_user_id") or "").strip()
        external_user_id = str(seed.get("external_user_id") or "").strip()
        if user_id or external_user_id:
            self.store_openwearables_identity(
                openwearables_user_id=user_id,
                external_user_id=external_user_id,
                secret=secret,
            )
        snapshot = seed.get("snapshot")
        if isinstance(snapshot, dict) and snapshot:
            self.save_wearables_cache(snapshot, secret=secret)
            self.record_wearables_runtime(
                snapshot=snapshot,
                status=str(snapshot.get("last_sync_status") or "ok"),
            )
            self.store_wearables_setup_state(
                enabled=bool(seed.get("enabled")),
                requested_providers=preferred_providers,
                connections=[
                    {"provider": provider, "status": "active"}
                    for provider in list(seed.get("connected_providers") or [])
                ],
                last_sync_at=str(snapshot.get("last_sync_at") or snapshot.get("generated_at") or ""),
                last_sync_status=str(snapshot.get("last_sync_status") or "ok"),
            )


def is_health_workspace(workspace: Path) -> bool:
    return (workspace / "health" / _PROFILE_NAME).exists()
