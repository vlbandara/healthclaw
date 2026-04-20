import asyncio
from datetime import UTC, datetime

import pytest

from nanobot.agent.memory import MemoryStore
from nanobot.health.storage import HealthWorkspace
from nanobot.heartbeat.service import HeartbeatService
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class DummyProvider(LLMProvider):
    def __init__(self, responses: list[LLMResponse]):
        super().__init__()
        self._responses = list(responses)
        self.calls = 0

    async def chat(self, *args, **kwargs) -> LLMResponse:
        self.calls += 1
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(content="", tool_calls=[])

    def get_default_model(self) -> str:
        return "test-model"


def _enable_health_workspace(
    tmp_path,
    *,
    timezone: str = "UTC",
    morning_check_in: bool = True,
    weekly_summary: bool = True,
) -> HealthWorkspace:
    health = HealthWorkspace(tmp_path)
    health.save_profile(
        {
            "mode": "health",
            "timezone": timezone,
            "preferred_channel": "telegram",
            "goals": ["Protect sleep"],
            "current_concerns": "Keep mornings steady",
            "preferences": {
                "morning_check_in": morning_check_in,
                "weekly_summary": weekly_summary,
                "reminder_preferences": [],
                "medication_reminder_windows": [],
            },
            "routines": {"wake_time": "07:00", "sleep_time": "22:30"},
            "friction_points": [],
            "communication_preferences": [],
            "last_open_loop": "none",
        }
    )
    (tmp_path / "HEARTBEAT.md").write_text("# Health Heartbeat\n", encoding="utf-8")
    return health


@pytest.mark.asyncio
async def test_start_is_idempotent(tmp_path) -> None:
    provider = DummyProvider([])

    service = HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="openai/gpt-4o-mini",
        interval_s=9999,
        enabled=True,
    )

    await service.start()
    first_task = service._task
    await service.start()

    assert service._task is first_task

    service.stop()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_decide_returns_skip_when_no_tool_call(tmp_path) -> None:
    provider = DummyProvider([LLMResponse(content="no tool call", tool_calls=[])])
    service = HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="openai/gpt-4o-mini",
    )

    action, tasks = await service._decide("heartbeat content")
    assert action == "skip"
    assert tasks == ""


@pytest.mark.asyncio
async def test_trigger_now_executes_when_decision_is_run(tmp_path) -> None:
    (tmp_path / "HEARTBEAT.md").write_text("- [ ] do thing", encoding="utf-8")

    provider = DummyProvider([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="hb_1",
                    name="heartbeat",
                    arguments={"action": "run", "tasks": "check open tasks"},
                )
            ],
        )
    ])

    called_with: list[str] = []

    async def _on_execute(tasks: str) -> str:
        called_with.append(tasks)
        return "done"

    service = HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="openai/gpt-4o-mini",
        on_execute=_on_execute,
    )

    result = await service.trigger_now()
    assert result == "done"
    assert called_with == ["check open tasks"]


@pytest.mark.asyncio
async def test_trigger_now_returns_none_when_decision_is_skip(tmp_path) -> None:
    (tmp_path / "HEARTBEAT.md").write_text("- [ ] do thing", encoding="utf-8")

    provider = DummyProvider([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="hb_1",
                    name="heartbeat",
                    arguments={"action": "skip"},
                )
            ],
        )
    ])

    async def _on_execute(tasks: str) -> str:
        return tasks

    service = HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="openai/gpt-4o-mini",
        on_execute=_on_execute,
    )

    assert await service.trigger_now() is None


@pytest.mark.asyncio
async def test_tick_notifies_when_evaluator_says_yes(tmp_path, monkeypatch) -> None:
    """Phase 1 run -> Phase 2 execute -> Phase 3 evaluate=notify -> on_notify called."""
    (tmp_path / "HEARTBEAT.md").write_text("- [ ] check deployments", encoding="utf-8")

    provider = DummyProvider([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="hb_1",
                    name="heartbeat",
                    arguments={"action": "run", "tasks": "check deployments"},
                )
            ],
        ),
    ])

    executed: list[str] = []
    notified: list[str] = []

    async def _on_execute(tasks: str) -> str:
        executed.append(tasks)
        return "deployment failed on staging"

    async def _on_notify(response: str) -> None:
        notified.append(response)

    service = HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="openai/gpt-4o-mini",
        on_execute=_on_execute,
        on_notify=_on_notify,
    )

    async def _eval_notify(*a, **kw):
        return True

    monkeypatch.setattr("nanobot.utils.evaluator.evaluate_response", _eval_notify)

    await service._tick()
    assert executed == ["check deployments"]
    assert notified == ["deployment failed on staging"]


@pytest.mark.asyncio
async def test_tick_suppresses_when_evaluator_says_no(tmp_path, monkeypatch) -> None:
    """Phase 1 run -> Phase 2 execute -> Phase 3 evaluate=silent -> on_notify NOT called."""
    (tmp_path / "HEARTBEAT.md").write_text("- [ ] check status", encoding="utf-8")

    provider = DummyProvider([
        LLMResponse(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="hb_1",
                    name="heartbeat",
                    arguments={"action": "run", "tasks": "check status"},
                )
            ],
        ),
    ])

    executed: list[str] = []
    notified: list[str] = []

    async def _on_execute(tasks: str) -> str:
        executed.append(tasks)
        return "everything is fine, no issues"

    async def _on_notify(response: str) -> None:
        notified.append(response)

    service = HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="openai/gpt-4o-mini",
        on_execute=_on_execute,
        on_notify=_on_notify,
    )

    async def _eval_silent(*a, **kw):
        return False

    monkeypatch.setattr("nanobot.utils.evaluator.evaluate_response", _eval_silent)

    await service._tick()
    assert executed == ["check status"]
    assert notified == []


@pytest.mark.asyncio
async def test_decide_retries_transient_error_then_succeeds(tmp_path, monkeypatch) -> None:
    provider = DummyProvider([
        LLMResponse(content="429 rate limit", finish_reason="error"),
        LLMResponse(
            content="",
            tool_calls=[
                ToolCallRequest(
                    id="hb_1",
                    name="heartbeat",
                    arguments={"action": "run", "tasks": "check open tasks"},
                )
            ],
        ),
    ])

    delays: list[int] = []

    async def _fake_sleep(delay: int) -> None:
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    service = HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="openai/gpt-4o-mini",
    )

    action, tasks = await service._decide("heartbeat content")

    assert action == "run"
    assert tasks == "check open tasks"
    assert provider.calls == 2
    assert delays == [1]


@pytest.mark.asyncio
async def test_decide_prompt_includes_current_time(tmp_path) -> None:
    """Phase 1 user prompt must contain current time so the LLM can judge task urgency."""

    captured_messages: list[dict] = []

    class CapturingProvider(LLMProvider):
        async def chat(self, *, messages=None, **kwargs) -> LLMResponse:
            if messages:
                captured_messages.extend(messages)
            return LLMResponse(
                content="",
                tool_calls=[
                    ToolCallRequest(
                        id="hb_1", name="heartbeat",
                        arguments={"action": "skip"},
                    )
                ],
            )

        def get_default_model(self) -> str:
            return "test-model"

    service = HeartbeatService(
        workspace=tmp_path,
        provider=CapturingProvider(),
        model="test-model",
    )

    await service._decide("- [ ] check servers at 10:00 UTC")

    user_msg = captured_messages[1]
    assert user_msg["role"] == "user"
    assert "Current Time:" in user_msg["content"]


@pytest.mark.asyncio
async def test_trigger_now_runs_interest_engagement_without_heartbeat_file(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    store.capture_interest_signals(
        "I love trail running and I am interested in neighborhood food spots.",
        timezone="UTC",
        now=datetime(2026, 4, 15, 9, 0, tzinfo=UTC),
    )
    state = store.read_engagement_state()
    state["last_user_message_at"] = datetime(2026, 4, 15, 9, 0, tzinfo=UTC).isoformat()
    store.write_engagement_state(state)

    executed: list[str] = []

    async def _on_execute(tasks: str) -> str:
        executed.append(tasks)
        return "Trail running check-in"

    service = HeartbeatService(
        workspace=tmp_path,
        provider=DummyProvider([]),
        model="openai/gpt-4o-mini",
        on_execute=_on_execute,
    )
    service._local_now = lambda: datetime(2026, 4, 19, 10, 0, tzinfo=UTC)  # type: ignore[method-assign]

    result = await service.trigger_now()

    assert result == "Trail running check-in"
    assert executed
    assert "Trail running" in executed[0]
    assert store.read_engagement_state()["delivery"]["recent_topics"] == ["Trail running"]


@pytest.mark.asyncio
async def test_interest_engagement_skips_when_user_was_recently_active(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    store.capture_interest_signals(
        "I enjoy chess and indie games.",
        timezone="UTC",
        now=datetime(2026, 4, 19, 8, 0, tzinfo=UTC),
    )
    store.record_user_activity(
        timezone="UTC",
        now=datetime(2026, 4, 19, 9, 30, tzinfo=UTC),
    )

    service = HeartbeatService(
        workspace=tmp_path,
        provider=DummyProvider([]),
        model="openai/gpt-4o-mini",
        on_execute=lambda tasks: _async_done(tasks),
    )
    service._local_now = lambda: datetime(2026, 4, 19, 10, 0, tzinfo=UTC)  # type: ignore[method-assign]

    assert await service.trigger_now() is None


@pytest.mark.asyncio
async def test_health_morning_checkin_suppressed_after_same_day_user_message(tmp_path, monkeypatch) -> None:
    health = _enable_health_workspace(tmp_path, weekly_summary=False)
    runtime = health.load_runtime()
    runtime["last_user_local_date"] = "2026-04-19"
    health.save_runtime(runtime)

    provider = DummyProvider([])
    executed: list[str] = []
    service = HeartbeatService(
        workspace=tmp_path,
        provider=provider,
        model="test-model",
        on_execute=lambda tasks: executed.append(tasks) or _async_done("done"),
    )
    monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 4, 19, 10, 30, tzinfo=UTC))

    assert await service.trigger_now() is None
    assert executed == []
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_health_morning_checkin_runs_once_per_local_day(tmp_path, monkeypatch) -> None:
    health = _enable_health_workspace(tmp_path, weekly_summary=False)
    executed: list[str] = []
    service = HeartbeatService(
        workspace=tmp_path,
        provider=DummyProvider([]),
        model="test-model",
        on_execute=lambda tasks: executed.append(tasks) or _async_done("done"),
    )
    monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 4, 19, 9, 0, tzinfo=UTC))

    assert await service.trigger_now() == "done"
    assert await service.trigger_now() is None
    assert len(executed) == 1
    assert health.load_runtime()["last_morning_checkin_sent_local_date"] == "2026-04-19"


@pytest.mark.asyncio
async def test_health_weekly_summary_runs_once_per_week_and_defers_late_night(tmp_path, monkeypatch) -> None:
    health = _enable_health_workspace(tmp_path, morning_check_in=False, weekly_summary=True)
    executed: list[str] = []
    service = HeartbeatService(
        workspace=tmp_path,
        provider=DummyProvider([]),
        model="test-model",
        on_execute=lambda tasks: executed.append(tasks) or _async_done("weekly"),
    )

    monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 4, 19, 22, 30, tzinfo=UTC))
    assert await service.trigger_now() is None

    monkeypatch.setattr(service, "_local_now", lambda: datetime(2026, 4, 19, 10, 0, tzinfo=UTC))
    assert await service.trigger_now() == "weekly"
    assert await service.trigger_now() is None
    assert len(executed) == 1
    assert health.load_runtime()["last_weekly_summary_sent_iso_week"] == "2026-W16"


async def _async_done(value: str) -> str:
    return value
