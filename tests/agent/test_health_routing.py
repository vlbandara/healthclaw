from pathlib import Path

from nanobot.agent.loop import AgentLoop, HealthModelRoute
from nanobot.bus.queue import MessageBus
from nanobot.config.schema import Config
from nanobot.health.storage import HealthWorkspace
from nanobot.providers.base import LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
    async def chat(self, *args, **kwargs) -> LLMResponse:
        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "MiniMax-M2.7"


def _make_loop(tmp_path: Path) -> AgentLoop:
    HealthWorkspace(tmp_path).save_profile(
        {
            "mode": "health",
            "timezone": "UTC",
            "preferred_channel": "telegram",
            "proactive_enabled": False,
        }
    )
    config = Config()
    config.agents.defaults.provider = "minimax"
    config.agents.defaults.model = "MiniMax-M2.7"
    config.providers.minimax.api_key = "minimax-key"
    config.providers.openrouter.api_key = "openrouter-key"
    return AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
        model="MiniMax-M2.7",
        runtime_config=config,
    )


def test_health_route_uses_primary_model_for_text_turn(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)

    route = loop._select_health_model_route()

    assert route == HealthModelRoute(
        provider_name="minimax",
        model="MiniMax-M2.7",
        reason="primary_text",
        fallback_provider_name="openrouter",
        fallback_model="openai/gpt-4o-mini",
    )


def test_health_route_uses_openrouter_for_image_turn(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    route = loop._select_health_model_route(media=[str(image_path)])

    assert route.provider_name == "openrouter"
    assert route.model == "openai/gpt-4o-mini"
    assert route.reason == "vision_input"


def test_health_route_force_fallback_uses_openrouter(tmp_path: Path) -> None:
    loop = _make_loop(tmp_path)

    route = loop._select_health_model_route(force_fallback=True)

    assert route.provider_name == "openrouter"
    assert route.model == "openai/gpt-4o-mini"
    assert route.reason == "fallback_text"
