"""Heartbeat service - periodic agent wake-up to check for tasks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Coroutine
from zoneinfo import ZoneInfo

from loguru import logger

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider

_HEARTBEAT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "heartbeat",
            "description": "Report heartbeat decision after reviewing tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["skip", "run"],
                        "description": "skip = nothing to do, run = has active tasks",
                    },
                    "tasks": {
                        "type": "string",
                        "description": "Natural-language summary of active tasks (required for run)",
                    },
                },
                "required": ["action"],
            },
        },
    }
]


@dataclass(slots=True)
class _HeartbeatPlan:
    action: str
    tasks: str
    source: str = "heartbeat"
    morning_checkin_sent: bool = False
    weekly_summary_sent: bool = False
    engagement_topic: str = ""


class HeartbeatService:
    """
    Periodic heartbeat service that wakes the agent to check for tasks.

    Phase 1 (decision): reads HEARTBEAT.md and asks the LLM — via a virtual
    tool call — whether there are active tasks.  This avoids free-text parsing
    and the unreliable HEARTBEAT_OK token.

    Phase 2 (execution): only triggered when Phase 1 returns ``run``.  The
    ``on_execute`` callback runs the task through the full agent loop and
    returns the result to deliver.
    """

    def __init__(
        self,
        workspace: Path,
        provider: LLMProvider,
        model: str,
        on_execute: Callable[[str], Coroutine[Any, Any, str]] | None = None,
        on_notify: Callable[[str], Coroutine[Any, Any, None]] | None = None,
        interval_s: int = 30 * 60,
        enabled: bool = True,
        timezone: str | None = None,
    ):
        self.workspace = workspace
        self.provider = provider
        self.model = model
        self.on_execute = on_execute
        self.on_notify = on_notify
        self.interval_s = interval_s
        self.enabled = enabled
        self.timezone = timezone
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def heartbeat_file(self) -> Path:
        return self.workspace / "HEARTBEAT.md"

    def _read_heartbeat_file(self) -> str | None:
        if self.heartbeat_file.exists():
            try:
                return self.heartbeat_file.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def _load_health(self):
        from nanobot.health.storage import HealthWorkspace

        return HealthWorkspace(self.workspace)

    @staticmethod
    def _render_health_tasks(*, tasks: list[str]) -> str:
        return "\n\n".join(tasks).strip()

    def _local_now(self) -> datetime:
        timezone = self._effective_timezone() or "UTC"
        now = datetime.now(UTC)
        try:
            tz = ZoneInfo(timezone)
        except Exception:
            return now.replace(tzinfo=None)
        return now.astimezone(tz)

    def _is_health_workspace(self) -> bool:
        try:
            from nanobot.health.storage import is_health_workspace

            return is_health_workspace(self.workspace)
        except Exception:
            return False

    def _build_health_plan(self) -> _HeartbeatPlan:
        health = self._load_health()
        profile = health.load_profile() or {}
        runtime = health.load_runtime()
        preferences = profile.get("preferences") or {}
        local_now = self._local_now()
        local_date = local_now.strftime("%Y-%m-%d")
        iso_year, iso_week, _ = local_now.isocalendar()
        iso_week_key = f"{iso_year}-W{iso_week:02d}"
        tasks: list[str] = []
        morning_due = False
        weekly_due = False

        wake_time = str((profile.get("routines") or {}).get("wake_time") or "07:00").strip() or "07:00"
        try:
            wake_hour, wake_minute = (int(part) for part in wake_time.split(":", 1))
        except Exception:
            wake_hour, wake_minute = 7, 0

        after_wake = (local_now.hour, local_now.minute) >= (wake_hour, wake_minute)
        already_engaged_today = str(runtime.get("last_user_local_date") or "").strip() == local_date
        morning_sent_today = str(runtime.get("last_morning_checkin_sent_local_date") or "").strip() == local_date
        if (
            bool(preferences.get("morning_check_in", True))
            and after_wake
            and not already_engaged_today
            and not morning_sent_today
        ):
            tasks.append(
                (
                    f"Morning check-in for {local_date} is due. "
                    f"Local time is {local_now.strftime('%H:%M')} and the wake-time trigger is {wake_time}. "
                    "Send one crisp, upbeat, forward-looking morning check-in with at most 3 questions and one concrete next move.\n"
                    "If goals or concerns are sparse, keep it exploratory and low-pressure.\n"
                    "Use the real session context and hidden memory already available in the main prompt "
                    "to avoid repeating questions from recent turns."
                )
            )
            morning_due = True

        weekly_sent = str(runtime.get("last_weekly_summary_sent_iso_week") or "").strip() == iso_week_key
        if (
            bool(preferences.get("weekly_summary", True))
            and local_now.weekday() == 6
            and local_now.hour < 21
            and not weekly_sent
        ):
            tasks.append(
                (
                    f"Weekly summary is due for ISO week {iso_week_key}. "
                    f"Local time is {local_now.strftime('%H:%M')} on Sunday. "
                    "Summarize sleep, stress, consistency, adherence, and movement briefly in the usual calm health-companion voice. "
                    "Keep it grounded, concise, and focused on one useful next step."
                )
            )
            weekly_due = True

        if not tasks:
            return _HeartbeatPlan(action="skip", tasks="")
        return _HeartbeatPlan(
            action="run",
            tasks=self._render_health_tasks(tasks=tasks),
            source="heartbeat",
            morning_checkin_sent=morning_due,
            weekly_summary_sent=weekly_due,
        )

    def _build_interest_plan(self) -> _HeartbeatPlan:
        from nanobot.agent.memory import MemoryStore

        store = MemoryStore(self.workspace)
        state = store.read_engagement_state()
        interest_memory = store.read_interest_memory().strip()
        if not interest_memory:
            return _HeartbeatPlan(action="skip", tasks="")

        reconnect_topics = [
            str(topic).strip()
            for topic in (state.get("reconnect_topics") or [])
            if str(topic).strip()
        ]
        if not reconnect_topics:
            return _HeartbeatPlan(action="skip", tasks="")

        local_now = self._local_now()
        local_date = local_now.strftime("%Y-%m-%d")
        last_user_message_at = str(state.get("last_user_message_at") or "").strip()
        if last_user_message_at:
            try:
                last_user = datetime.fromisoformat(last_user_message_at)
                if (local_now.replace(tzinfo=None) - last_user.replace(tzinfo=None)).total_seconds() < 48 * 60 * 60:
                    return _HeartbeatPlan(action="skip", tasks="")
            except Exception:
                pass

        delivery = state.get("delivery") or {}
        if str(delivery.get("last_sent_local_date") or "").strip() == local_date:
            return _HeartbeatPlan(action="skip", tasks="")

        recent_topics = {
            str(topic).strip().lower()
            for topic in (delivery.get("recent_topics") or [])[-3:]
            if str(topic).strip()
        }
        topic = next((item for item in reconnect_topics if item.lower() not in recent_topics), reconnect_topics[0])
        tasks = (
            "Send one short, natural reconnect message in your normal voice.\n"
            f"Re-open this user interest only if it feels human and low-pressure: {topic}\n"
            "Use the real session context and hidden interest memory already available in the main prompt.\n"
            "Do not mention research, internal systems, files, hidden memory, or why you chose the topic."
        )
        return _HeartbeatPlan(
            action="run",
            tasks=tasks,
            source="interest_memory",
            engagement_topic=topic,
        )

    async def _plan_tick(self, content: str | None) -> _HeartbeatPlan:
        plan = _HeartbeatPlan(action="skip", tasks="")
        if self._is_health_workspace():
            plan = self._build_health_plan()
        elif content:
            action, tasks = await self._decide(content)
            plan = _HeartbeatPlan(action=action, tasks=tasks)
        if plan.action != "run":
            plan = self._build_interest_plan()
        return plan

    def _effective_timezone(self) -> str | None:
        try:
            from nanobot.health.storage import HealthWorkspace, is_health_workspace

            if is_health_workspace(self.workspace):
                profile = HealthWorkspace(self.workspace).load_profile() or {}
                timezone = str(profile.get("timezone") or "").strip()
                if timezone:
                    return timezone
        except Exception:
            pass
        return self.timezone

    async def _decide(self, content: str) -> tuple[str, str]:
        """Phase 1: ask LLM to decide skip/run via virtual tool call.

        Returns (action, tasks) where action is 'skip' or 'run'.
        """
        from nanobot.utils.helpers import current_time_str

        response = await self.provider.chat_with_retry(
            messages=[
                {"role": "system", "content": "You are a heartbeat agent. Call the heartbeat tool to report your decision."},
                {"role": "user", "content": (
                    f"Current Time: {current_time_str(self._effective_timezone())}\n\n"
                    "Review the following HEARTBEAT.md and decide whether there are active tasks.\n\n"
                    f"{content}"
                )},
            ],
            tools=_HEARTBEAT_TOOL,
            model=self.model,
        )

        if not response.has_tool_calls:
            return "skip", ""

        args = response.tool_calls[0].arguments
        return args.get("action", "skip"), args.get("tasks", "")

    async def start(self) -> None:
        """Start the heartbeat service."""
        if not self.enabled:
            logger.info("Heartbeat disabled")
            return
        if self._running:
            logger.warning("Heartbeat already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Heartbeat started (every {}s)", self.interval_s)

    def stop(self) -> None:
        """Stop the heartbeat service."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        """Main heartbeat loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Heartbeat error: {}", e)

    async def tick_once(self) -> None:
        """Run one heartbeat decision + optional execute/notify cycle (for multi-tenant)."""
        await self._tick()

    async def _tick(self) -> None:
        """Execute a single heartbeat tick."""
        from nanobot.utils.evaluator import evaluate_response

        content = self._read_heartbeat_file()
        if not content and not self._build_interest_plan().tasks:
            logger.debug("Heartbeat: HEARTBEAT.md missing or empty")
            return

        logger.info("Heartbeat: checking for tasks...")

        try:
            plan = await self._plan_tick(content)

            if plan.action != "run":
                logger.info("Heartbeat: OK (nothing to report)")
                return

            logger.info("Heartbeat: tasks found, executing...")
            if self.on_execute:
                response = await self.on_execute(plan.tasks)

                if response:
                    should_notify = await evaluate_response(
                        response, plan.tasks, self.provider, self.model,
                    )
                    if should_notify and self.on_notify:
                        logger.info("Heartbeat: completed, delivering response")
                        await self.on_notify(response)
                        if self._is_health_workspace():
                            self._load_health().record_proactive_delivery(
                                source=plan.source,
                                now=self._local_now(),
                                morning_checkin_sent=plan.morning_checkin_sent,
                                weekly_summary_sent=plan.weekly_summary_sent,
                            )
                        if plan.engagement_topic:
                            from nanobot.agent.memory import MemoryStore

                            MemoryStore(self.workspace).record_engagement_delivery(
                                topic=plan.engagement_topic,
                                timezone=self._effective_timezone(),
                                now=self._local_now(),
                            )
                    else:
                        logger.info("Heartbeat: silenced by post-run evaluation")
        except Exception:
            logger.exception("Heartbeat execution failed")

    async def trigger_now(self) -> str | None:
        """Manually trigger a heartbeat."""
        content = self._read_heartbeat_file()
        if not content and not self._build_interest_plan().tasks:
            return None
        plan = await self._plan_tick(content)
        if plan.action != "run" or not self.on_execute:
            return None
        result = await self.on_execute(plan.tasks)
        if result:
            if self._is_health_workspace():
                self._load_health().record_proactive_delivery(
                    source=plan.source,
                    now=self._local_now(),
                    morning_checkin_sent=plan.morning_checkin_sent,
                    weekly_summary_sent=plan.weekly_summary_sent,
                )
            if plan.engagement_topic:
                from nanobot.agent.memory import MemoryStore

                MemoryStore(self.workspace).record_engagement_delivery(
                    topic=plan.engagement_topic,
                    timezone=self._effective_timezone(),
                    now=self._local_now(),
                )
        return result
