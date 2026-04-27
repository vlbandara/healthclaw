from __future__ import annotations

import pytest

from nanobot.health import openwearables as ow_mod
from nanobot.health.storage import HealthWorkspace


class _FakeOpenWearablesClient:
    def __init__(self) -> None:
        self.synced: list[str] = []

    async def list_enabled_providers(self) -> list[dict[str, object]]:
        return [
            {"provider": "garmin", "name": "Garmin", "is_enabled": True, "has_cloud_api": True},
            {"provider": "polar", "name": "Polar", "is_enabled": True, "has_cloud_api": True},
        ]

    async def get_or_create_user(self, *, external_user_id: str, email: str = "", display_name: str = "") -> dict[str, object]:
        return {"id": "ow-user-123", "external_user_id": external_user_id, "email": email, "display_name": display_name}

    async def authorize_provider(self, *, provider: str, user_id: str, redirect_uri: str) -> dict[str, object]:
        return {
            "authorization_url": f"https://wearables.example.test/oauth/{provider}",
            "state": "oauth-state-123",
            "user_id": user_id,
            "redirect_uri": redirect_uri,
        }

    async def list_connections(self, user_id: str) -> list[dict[str, object]]:
        return [
            {"provider": "garmin", "status": "active", "last_synced_at": "2026-04-27T10:30:00Z"},
        ]

    async def sync_provider(self, *, provider: str, user_id: str) -> dict[str, object]:
        self.synced.append(provider)
        return {"status": "ok"}

    async def fetch_snapshot(self, *, user_id: str, connections=None) -> ow_mod.WearableSnapshot:
        return ow_mod.WearableSnapshot(
            generated_at="2026-04-27T10:35:00Z",
            connected_providers=["garmin"],
            last_sync_at="2026-04-27T10:30:00Z",
            freshness="fresh",
            freshness_note="fresh (0h since last sync)",
            summaries={"sleep": {"date": "2026-04-27", "score": 82, "duration_h": 7.4}},
            health_scores={"sleep_score": 82, "recovery_score": 74},
            trend_flags=["sleep score improved versus the prior day"],
            notes=[],
        )


@pytest.mark.asyncio
async def test_start_wearable_authorization_persists_encrypted_mapping(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEALTH_VAULT_KEY", "test-health-vault-key")
    monkeypatch.setenv("OPENWEARABLES_API_URL", "https://wearables.example.test")
    monkeypatch.setenv("OPENWEARABLES_API_KEY", "ow-secret-key")
    fake = _FakeOpenWearablesClient()
    monkeypatch.setattr(ow_mod.OpenWearablesClient, "from_env", classmethod(lambda cls: fake))

    health = HealthWorkspace(tmp_path)
    health.create_setup_session_with_token("setup-wearables")

    authorization = await ow_mod.start_wearable_authorization(
        health,
        provider="garmin",
        external_user_id="setup-wearables",
        redirect_uri="https://health.example.test/api/setup/setup-wearables/wearables/callback",
        email="jane@example.com",
        display_name="Jane Doe",
        secret="test-health-vault-key",
    )

    assert authorization["authorization_url"].endswith("/garmin")
    assert health.load_setup()["wearables"]["requested_providers"] == ["garmin"]
    assert health.load_openwearables_identity(secret="test-health-vault-key") == {
        "openwearables_user_id": "ow-user-123",
        "external_user_id": "setup-wearables",
    }
    ciphertext = health.setup_secrets_path.read_text(encoding="utf-8")
    assert "ow-user-123" not in ciphertext
    assert "setup-wearables" not in ciphertext


@pytest.mark.asyncio
async def test_sync_wearable_snapshot_persists_cache_and_runtime(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEALTH_VAULT_KEY", "test-health-vault-key")
    monkeypatch.setenv("OPENWEARABLES_API_URL", "https://wearables.example.test")
    monkeypatch.setenv("OPENWEARABLES_API_KEY", "ow-secret-key")
    fake = _FakeOpenWearablesClient()
    monkeypatch.setattr(ow_mod.OpenWearablesClient, "from_env", classmethod(lambda cls: fake))

    health = HealthWorkspace(tmp_path)
    health.create_setup_session_with_token("setup-wearables")
    health.store_openwearables_identity(
        openwearables_user_id="ow-user-123",
        external_user_id="setup-wearables",
        secret="test-health-vault-key",
    )

    snapshot = await ow_mod.sync_wearable_snapshot(
        health,
        provider=None,
        secret="test-health-vault-key",
    )

    assert snapshot.connected_providers == ["garmin"]
    assert fake.synced == ["garmin"]
    cache = health.load_wearables_cache(secret="test-health-vault-key")
    assert cache is not None
    assert cache["summaries"]["sleep"]["score"] == 82
    setup = health.load_setup()
    assert setup["wearables"]["connected_providers"] == ["garmin"]
    assert setup["wearables"]["last_sync_status"] == "ok"
    runtime = health.load_runtime()
    assert runtime["wearables"]["connected_providers"] == ["garmin"]
    assert runtime["wearables"]["last_sync_status"] == "ok"
