from __future__ import annotations

from nanobot.health.spawner import HealthInstanceSpawner


def test_spawner_defaults_to_biomeclaw_orchestrator_image(monkeypatch) -> None:
    monkeypatch.delenv("NANOBOT_HEALTH_INSTANCE_IMAGE", raising=False)

    spawner = HealthInstanceSpawner()

    assert spawner.image == "biomeclaw-orchestrator:latest"


def test_spawner_resolves_current_container_network(monkeypatch) -> None:
    monkeypatch.delenv("NANOBOT_HEALTH_INSTANCE_NETWORK", raising=False)
    monkeypatch.setenv("HOSTNAME", "orchestrator-container")

    class _FakeContainers:
        def get(self, _name: str):
            return type(
                "_FakeContainer",
                (),
                {
                    "attrs": {
                        "NetworkSettings": {
                            "Networks": {
                                "bridge": {},
                                "biomeclaw_default": {},
                            }
                        }
                    }
                },
            )()

    class _FakeClient:
        containers = _FakeContainers()

    spawner = HealthInstanceSpawner()
    monkeypatch.setattr(spawner, "_client", lambda: _FakeClient())

    assert spawner._resolve_network() == "biomeclaw_default"


def test_spawner_prefers_explicit_network(monkeypatch) -> None:
    monkeypatch.setenv("NANOBOT_HEALTH_INSTANCE_NETWORK", "custom-health-net")

    spawner = HealthInstanceSpawner()

    assert spawner._resolve_network() == "custom-health-net"
