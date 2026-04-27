from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("starlette")

from fastapi.testclient import TestClient

from nanobot.health.api import create_app
from nanobot.health.spawner import SpawnResult
from nanobot.health.storage import HealthWorkspace


def _payload(*, preferred_channel: str = "telegram") -> dict:
    return {
        "phase1": {
            "full_name": "Jane Doe",
            "location": "Colombo, Sri Lanka",
            "email": "jane@example.com",
            "phone": "+15550001111",
            "timezone": "Asia/Colombo",
            "language": "en",
            "preferred_channel": preferred_channel,
            "age_range": "35-44",
            "sex": "female",
            "gender": "woman",
            "height_cm": 165,
            "weight_kg": 62,
            "known_conditions": ["asthma"],
            "medications": ["albuterol"],
            "allergies": ["penicillin"],
            "wake_time": "06:30",
            "sleep_time": "22:30",
            "consents": ["privacy", "emergency", "coaching"],
        },
        "phase2": {
            "mood_interest": 1,
            "mood_down": 0,
            "activity_level": "moderate",
            "nutrition_quality": "mixed",
            "sleep_quality": "fair",
            "stress_level": "moderate",
            "goals": ["improve sleep"],
            "current_concerns": "Waking up tired",
            "reminder_preferences": ["morning check-in"],
            "medication_reminder_windows": ["08:00", "20:00"],
            "morning_check_in": True,
            "weekly_summary": True,
        },
    }


def _make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, HealthWorkspace]:
    monkeypatch.delenv("NANOBOT_HEALTH_REGISTRY_URL", raising=False)
    monkeypatch.setenv("NANOBOT_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("HEALTH_VAULT_KEY", "test-health-vault-key")
    monkeypatch.setenv("HEALTH_TELEGRAM_BOT_URL", "https://t.me/example_bot")
    monkeypatch.setenv("HEALTH_WHATSAPP_CHAT_URL", "https://wa.me/15550001111")
    monkeypatch.setenv("NANOBOT_HEALTH_REGISTRY_PATH", str(tmp_path / "health-registry.sqlite3"))
    health = HealthWorkspace(tmp_path)
    app = create_app()
    return TestClient(app), health


def _setup_session_health(tmp_path: Path, token: str) -> HealthWorkspace:
    return HealthWorkspace(tmp_path / "health-staging" / token)


def test_setup_page_and_provider_submission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    token = "setup-page-token"
    health = _setup_session_health(tmp_path, token)
    health.create_setup_session_with_token(token)
    monkeypatch.setattr(
        "nanobot.health.api.validate_provider_credentials",
        AsyncMock(return_value={"provider": "minimax", "label": "MiniMax", "model": "MiniMax-M2.7"}),
    )

    page = client.get(f"/setup/{token}")
    assert page.status_code == 200
    assert "Give your companion a place to reach you." in page.text
    assert "Connect Telegram" in page.text
    assert "Scan with WhatsApp" not in page.text
    assert "Timezone" in page.text

    resp = client.post(
        f"/api/setup/{token}/provider",
        json={"provider": "minimax", "api_key": "minimax-secret-key"},
    )
    assert resp.status_code == 200
    setup = health.load_setup()
    assert setup["provider"]["validated_at"]
    assert setup["provider"]["provider"] == "minimax"
    ciphertext = health.setup_secrets_path.read_text(encoding="utf-8")
    assert "minimax-secret-key" not in ciphertext


def test_setup_activate_with_telegram(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    token = "setup-telegram-token"
    health = _setup_session_health(tmp_path, token)
    health.create_setup_session_with_token(token)
    monkeypatch.setattr(
        "nanobot.health.api.validate_provider_credentials",
        AsyncMock(return_value={"provider": "minimax", "label": "MiniMax", "model": "MiniMax-M2.7"}),
    )
    monkeypatch.setattr(
        "nanobot.health.api.validate_telegram_bot_token",
        AsyncMock(
            return_value={
                "bot_id": 123456,
                "bot_username": "healthbot_test",
                "bot_name": "Health Bot",
                "bot_url": "https://t.me/healthbot_test",
            }
        ),
    )
    register = AsyncMock()
    monkeypatch.setattr("nanobot.health.api.register_telegram_commands", register)
    monkeypatch.setattr(client.app.state.registry, "get_by_setup_token", AsyncMock(return_value=None))
    monkeypatch.setattr(client.app.state.registry, "set_container", AsyncMock(return_value=None))
    monkeypatch.setattr(
        client.app.state.spawner,
        "spawn_instance",
        lambda **_kwargs: SpawnResult(
            container_id="ctr-test-123",
            volume_name="vol-test-123",
            workspace_path=str(tmp_path / "spawned-instance"),
        ),
    )

    assert client.post(
        f"/api/setup/{token}/provider",
        json={"provider": "minimax", "api_key": "minimax-secret-key"},
    ).status_code == 200
    assert client.post(
        f"/api/setup/{token}/channels/telegram",
        json={"bot_token": "123:abc"},
    ).status_code == 200
    assert client.post(f"/api/setup/{token}/profile", json=_payload()).status_code == 200

    resp = client.post(f"/api/setup/{token}/activate")
    assert resp.status_code == 200
    assert resp.json()["state"] == "active"
    assert resp.json()["channelLinks"]["telegram"] == "https://t.me/healthbot_test"
    profile = json.loads((tmp_path / "health" / "profile.json").read_text(encoding="utf-8"))
    assert profile["user_token"] == token
    assert profile["preferred_channel"] == "telegram"
    assert profile["location"] == "Colombo, Sri Lanka"
    assert profile["timezone"] == "Asia/Colombo"
    assert health.load_setup()["state"] == "active"
    register.assert_awaited_once()


def test_signup_reuses_valid_unfinished_setup_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)

    first = client.post("/api/signup", json={"name": "Jane", "timezone": "Asia/Colombo"})
    assert first.status_code == 200
    setup_token = first.json()["setupToken"]
    user_id = first.json()["userId"]

    resumed = client.post(
        "/api/signup",
        json={"name": "Jane", "timezone": "Asia/Colombo", "resumeSetupToken": setup_token},
    )

    assert resumed.status_code == 200
    assert resumed.json()["setupToken"] == setup_token
    assert resumed.json()["userId"] == user_id
    assert resumed.json()["resumed"] is True


def test_setup_activate_with_whatsapp_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    token = "setup-whatsapp-primary-token"
    health = _setup_session_health(tmp_path, token)
    health.create_setup_session_with_token(token)
    monkeypatch.setattr(
        "nanobot.health.api.validate_provider_credentials",
        AsyncMock(return_value={"provider": "minimax", "label": "MiniMax", "model": "MiniMax-M2.7"}),
    )
    register = AsyncMock()
    monkeypatch.setattr("nanobot.health.api.register_telegram_commands", register)
    monkeypatch.setattr(client.app.state.registry, "get_by_setup_token", AsyncMock(return_value=None))
    monkeypatch.setattr(client.app.state.registry, "set_container", AsyncMock(return_value=None))
    monkeypatch.setattr(
        client.app.state.spawner,
        "spawn_instance",
        lambda **_kwargs: SpawnResult(
            container_id="ctr-test-wa-123",
            volume_name="vol-test-wa-123",
            workspace_path=str(tmp_path / "spawned-instance"),
        ),
    )
    client.app.state.whatsapp_monitor._snapshot.update(
        {
            "status": "connected",
            "qr": "",
            "jid": "15550001111@s.whatsapp.net",
            "phone": "15550001111",
            "chat_url": "https://wa.me/15550001111",
        }
    )

    assert client.post(
        f"/api/setup/{token}/provider",
        json={"provider": "minimax", "api_key": "minimax-secret-key"},
    ).status_code == 200
    assert client.post(f"/api/setup/{token}/profile", json=_payload(preferred_channel="whatsapp")).status_code == 200

    resp = client.post(f"/api/setup/{token}/activate")
    assert resp.status_code == 200
    assert resp.json()["state"] == "active"
    assert resp.json()["preferredChannel"] == "whatsapp"
    assert resp.json()["channelLinks"]["whatsapp"] == "https://wa.me/15550001111"
    profile = json.loads((tmp_path / "health" / "profile.json").read_text(encoding="utf-8"))
    assert profile["user_token"] == token
    assert profile["preferred_channel"] == "whatsapp"
    register.assert_not_awaited()


def test_setup_profile_allows_manual_timezone_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    token = "setup-timezone-token"
    health = _setup_session_health(tmp_path, token)
    health.create_setup_session_with_token(token)
    payload = _payload()
    payload["phase1"]["timezone"] = "America/New_York"

    response = client.post(f"/api/setup/{token}/profile", json=payload)

    assert response.status_code == 200
    stored = health.load_profile_draft_submission(secret="test-health-vault-key")
    assert stored is not None
    assert stored["phase1"]["timezone"] == "America/New_York"


def test_setup_wearables_connect_and_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    token = "setup-wearables-token"
    health = _setup_session_health(tmp_path, token)
    health.create_setup_session_with_token(token)
    monkeypatch.setenv("OPENWEARABLES_API_URL", "https://wearables.example.test")
    monkeypatch.setenv("OPENWEARABLES_API_KEY", "ow-secret-key")

    class _FakeOpenWearablesClient:
        async def list_enabled_providers(self):
            return [{"provider": "garmin", "name": "Garmin", "is_enabled": True, "has_cloud_api": True}]

        async def get_or_create_user(self, *, external_user_id: str, email: str = "", display_name: str = ""):
            return {"id": "ow-user-123", "external_user_id": external_user_id}

        async def authorize_provider(self, *, provider: str, user_id: str, redirect_uri: str):
            return {"authorization_url": "https://wearables.example.test/oauth/garmin", "state": "abc123"}

        async def list_connections(self, user_id: str):
            return [{"provider": "garmin", "status": "active", "last_synced_at": "2026-04-27T10:30:00Z"}]

        async def sync_provider(self, *, provider: str, user_id: str):
            return {"status": "ok"}

        async def fetch_snapshot(self, *, user_id: str, connections=None):
            from nanobot.health.openwearables import WearableSnapshot

            return WearableSnapshot(
                generated_at="2026-04-27T10:35:00Z",
                connected_providers=["garmin"],
                last_sync_at="2026-04-27T10:30:00Z",
                freshness="fresh",
                freshness_note="fresh (0h since last sync)",
                summaries={"sleep": {"date": "2026-04-27", "score": 81}},
                health_scores={"sleep_score": 81},
                trend_flags=["sleep score improved versus the prior day"],
                notes=[],
            )

    fake = _FakeOpenWearablesClient()
    monkeypatch.setattr(
        "nanobot.health.openwearables.OpenWearablesClient.from_env",
        classmethod(lambda cls: fake),
    )

    providers = client.get(f"/api/setup/{token}/wearables/providers")
    assert providers.status_code == 200
    assert providers.json()["providers"][0]["provider"] == "garmin"

    connect = client.post(f"/api/setup/{token}/wearables/connect", json={"provider": "garmin"})
    assert connect.status_code == 200
    assert connect.json()["authorizationUrl"] == "https://wearables.example.test/oauth/garmin"

    status = client.get(f"/api/setup/{token}/wearables/status")
    assert status.status_code == 200
    assert status.json()["wearables"]["connected_providers"] == ["garmin"]

    sync = client.post(f"/api/setup/{token}/wearables/sync", json={"provider": ""})
    assert sync.status_code == 200
    assert sync.json()["snapshot"]["connected_providers"] == ["garmin"]

    root_status = client.get(f"/api/setup/{token}/status")
    assert root_status.status_code == 200
    assert root_status.json()["wearables"]["connected_providers"] == ["garmin"]
    ciphertext = health.setup_secrets_path.read_text(encoding="utf-8")
    assert "ow-user-123" not in ciphertext


def test_setup_rejects_activation_without_connected_channel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    token = "setup-no-channel-token"
    health = _setup_session_health(tmp_path, token)
    health.create_setup_session_with_token(token)
    monkeypatch.setattr(
        "nanobot.health.api.validate_provider_credentials",
        AsyncMock(return_value={"provider": "minimax", "label": "MiniMax", "model": "MiniMax-M2.7"}),
    )

    assert client.post(
        f"/api/setup/{token}/provider",
        json={"provider": "minimax", "api_key": "minimax-secret-key"},
    ).status_code == 200
    assert client.post(f"/api/setup/{token}/profile", json=_payload()).status_code == 200

    resp = client.post(f"/api/setup/{token}/activate")
    assert resp.status_code == 400
    assert "Connect Telegram or WhatsApp before continuing." in resp.json()["detail"]


def test_setup_whatsapp_status_uses_bridge_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    token = "setup-whatsapp-token"
    health = _setup_session_health(tmp_path, token)
    health.create_setup_session_with_token(token)
    monkeypatch.setenv("MINIMAX_API_KEY", "env-minimax-key")
    client.app.state.whatsapp_monitor._snapshot.update(
        {
            "status": "connected",
            "qr": "",
            "jid": "15550001111@s.whatsapp.net",
            "phone": "15550001111",
            "chat_url": "https://wa.me/15550001111",
        }
    )

    resp = client.get(f"/api/setup/{token}/channels/whatsapp/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "connected"
    status_resp = client.get(f"/api/setup/{token}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["activationReady"] is True
    setup = health.load_setup()
    assert setup["channels"]["whatsapp"]["connected"] is True

    qr_resp = client.get(f"/api/setup/{token}/channels/whatsapp/qr")
    assert qr_resp.status_code == 200
    assert qr_resp.json()["chatUrl"] == "https://wa.me/15550001111"


def test_setup_allows_openrouter_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    token = "setup-openrouter-token"
    health = _setup_session_health(tmp_path, token)
    health.create_setup_session_with_token(token)
    monkeypatch.setattr(
        "nanobot.health.api.validate_provider_credentials",
        AsyncMock(
            return_value={
                "provider": "openrouter",
                "label": "OpenRouter",
                "model": "openai/gpt-4o-mini",
            }
        ),
    )

    resp = client.post(
        f"/api/setup/{token}/provider",
        json={"provider": "openrouter", "api_key": "sk-or-test"},
    )

    assert resp.status_code == 200
    setup = health.load_setup()
    assert setup["provider"]["provider"] == "openrouter"
    assert setup["provider"]["model"] == "openai/gpt-4o-mini"


def test_setup_activate_spawn_failure_returns_reference_and_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    token = "setup-spawn-failure-token"
    health = _setup_session_health(tmp_path, token)
    health.create_setup_session_with_token(token)
    monkeypatch.setattr(
        "nanobot.health.api.validate_provider_credentials",
        AsyncMock(return_value={"provider": "minimax", "label": "MiniMax", "model": "MiniMax-M2.7"}),
    )
    monkeypatch.setattr(
        "nanobot.health.api.validate_telegram_bot_token",
        AsyncMock(
            return_value={
                "bot_id": 123456,
                "bot_username": "healthbot_test",
                "bot_name": "Health Bot",
                "bot_url": "https://t.me/healthbot_test",
            }
        ),
    )
    monkeypatch.setattr("nanobot.health.api.register_telegram_commands", AsyncMock(return_value=None))
    monkeypatch.setattr(client.app.state.registry, "get_by_setup_token", AsyncMock(return_value=None))
    monkeypatch.setattr(
        client.app.state.spawner,
        "spawn_instance",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("docker unavailable")),
    )
    caplog.set_level(logging.ERROR, logger="nanobot.health.api")

    assert client.post(
        f"/api/setup/{token}/provider",
        json={"provider": "minimax", "api_key": "minimax-secret-key"},
    ).status_code == 200
    assert client.post(
        f"/api/setup/{token}/channels/telegram",
        json={"bot_token": "123:abc"},
    ).status_code == 200
    assert client.post(f"/api/setup/{token}/profile", json=_payload()).status_code == 200

    response = client.post(
        f"/api/setup/{token}/activate",
        headers={"X-Request-ID": "req-activate-1"},
    )

    assert response.status_code == 502
    assert response.headers["X-Request-ID"] == "req-activate-1"
    assert response.json()["requestId"] == "req-activate-1"
    assert response.json()["errorId"] == "req-activate-1"
    assert "Unable to start your coach" in response.json()["detail"]
    metrics = client.get("/metrics").json()
    assert metrics["runtime"]["lastError"]["requestId"] == "req-activate-1"
    assert metrics["runtime"]["lastError"]["statusCode"] == 502

    error_records = [record for record in caplog.records if record.msg == "activate.spawn_failed"]
    assert error_records
    assert getattr(error_records[0], "request_id", "") == "req-activate-1"
