"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import time
from contextlib import AsyncExitStack, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.hook import AgentHook, AgentHookContext, CompositeHook
from nanobot.agent.memory import Consolidator, Dream
from nanobot.agent.runner import AgentRunner, AgentRunSpec
from nanobot.agent.skills import BUILTIN_SKILLS_DIR
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.health_onboarding import CompleteOnboardingTool
from nanobot.agent.tools.health_profile import SetPreferredNameTool, UpdateHealthProfileTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.search import GlobTool, GrepTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.command import CommandContext, CommandRouter, register_builtin_commands
from nanobot.config.schema import AgentDefaults
from nanobot.health.bootstrap import read_tenant_user_token
from nanobot.health.continuity import (
    apply_health_continuity_updates,
    build_health_behavior_overlay,
    build_temporal_context,
    extract_health_continuity_facts,
    select_opening_style,
    select_variation_mode,
)
from nanobot.health.openwearables import wearable_context_lines
from nanobot.health.safety import emergency_response, is_emergency_language
from nanobot.health.storage import HealthWorkspace, health_distribution_enabled, is_health_workspace
from nanobot.providers.base import GenerationSettings, LLMProvider
from nanobot.providers.registry import find_by_name
from nanobot.session.manager import Session, SessionManager
from nanobot.utils.helpers import detect_image_mime, image_placeholder_text, truncate_text
from nanobot.utils.prompt_templates import render_template
from nanobot.utils.runtime import EMPTY_FINAL_RESPONSE_MESSAGE

if TYPE_CHECKING:
    from nanobot.config.schema import ChannelsConfig, Config, ExecToolConfig, WebToolsConfig
    from nanobot.cron.service import CronService


@dataclass(frozen=True, slots=True)
class HealthModelRoute:
    """Internal provider/model choice for a health turn."""

    provider_name: str
    model: str
    reason: str
    fallback_provider_name: str | None = None
    fallback_model: str | None = None


class _LoopHook(AgentHook):
    """Core hook for the main loop."""

    def __init__(
        self,
        agent_loop: AgentLoop,
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        *,
        channel: str = "cli",
        chat_id: str = "direct",
        message_id: str | None = None,
    ) -> None:
        self._loop = agent_loop
        self._on_progress = on_progress
        self._on_stream = on_stream
        self._on_stream_end = on_stream_end
        self._channel = channel
        self._chat_id = chat_id
        self._message_id = message_id
        self._stream_buf = ""

    def wants_streaming(self) -> bool:
        return self._on_stream is not None

    async def on_stream(self, context: AgentHookContext, delta: str) -> None:
        from nanobot.utils.helpers import strip_think

        prev_clean = strip_think(self._stream_buf)
        self._stream_buf += delta
        new_clean = strip_think(self._stream_buf)
        incremental = new_clean[len(prev_clean):]
        if incremental and self._on_stream:
            await self._on_stream(incremental)

    async def on_stream_end(self, context: AgentHookContext, *, resuming: bool) -> None:
        if self._on_stream_end:
            await self._on_stream_end(resuming=resuming)
        self._stream_buf = ""

    async def before_execute_tools(self, context: AgentHookContext) -> None:
        if self._on_progress:
            if not self._on_stream:
                thought = self._loop._strip_think(
                    context.response.content if context.response else None
                )
                if thought:
                    await self._on_progress(thought)
            tool_hint = self._loop._strip_think(self._loop._tool_hint(context.tool_calls))
            await self._on_progress(tool_hint, tool_hint=True)
        for tc in context.tool_calls:
            args_str = json.dumps(tc.arguments, ensure_ascii=False)
            logger.info("Tool call: {}({})", tc.name, args_str[:200])
        self._loop._set_tool_context(self._channel, self._chat_id, self._message_id)

    async def after_iteration(self, context: AgentHookContext) -> None:
        u = context.usage or {}
        logger.debug(
            "LLM usage: prompt={} completion={} cached={}",
            u.get("prompt_tokens", 0),
            u.get("completion_tokens", 0),
            u.get("cached_tokens", 0),
        )

    def finalize_content(self, context: AgentHookContext, content: str | None) -> str | None:
        return self._loop._strip_think(content)


class _LoopHookChain(AgentHook):
    """Run the core hook before extra hooks."""

    __slots__ = ("_primary", "_extras")

    def __init__(self, primary: AgentHook, extra_hooks: list[AgentHook]) -> None:
        self._primary = primary
        self._extras = CompositeHook(extra_hooks)

    def wants_streaming(self) -> bool:
        return self._primary.wants_streaming() or self._extras.wants_streaming()

    async def before_iteration(self, context: AgentHookContext) -> None:
        await self._primary.before_iteration(context)
        await self._extras.before_iteration(context)

    async def on_stream(self, context: AgentHookContext, delta: str) -> None:
        await self._primary.on_stream(context, delta)
        await self._extras.on_stream(context, delta)

    async def on_stream_end(self, context: AgentHookContext, *, resuming: bool) -> None:
        await self._primary.on_stream_end(context, resuming=resuming)
        await self._extras.on_stream_end(context, resuming=resuming)

    async def before_execute_tools(self, context: AgentHookContext) -> None:
        await self._primary.before_execute_tools(context)
        await self._extras.before_execute_tools(context)

    async def after_iteration(self, context: AgentHookContext) -> None:
        await self._primary.after_iteration(context)
        await self._extras.after_iteration(context)

    def finalize_content(self, context: AgentHookContext, content: str | None) -> str | None:
        content = self._primary.finalize_content(context, content)
        return self._extras.finalize_content(context, content)


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _RUNTIME_CHECKPOINT_KEY = "runtime_checkpoint"
    _HEALTH_TRIVIAL_EXACT = {
        "",
        "hi",
        "hey",
        "hello",
        "yo",
        "sup",
        "good",
        "ok",
        "okay",
        "yes",
        "no",
        "me",
        "me?",
        "who are you",
        "what do you know about me",
        "what you know about me",
    }
    _HEALTH_TRIVIAL_PREFIXES = (
        "hi ",
        "hey ",
        "hello ",
        "what do you know about me",
        "what you know about me",
        "do you know me",
        "you know me",
        "do you know my name",
        "do you want my name",
        "do you wanna my name",
        "my name is ",
        "call me ",
        "i'm ",
        "im ",
    )
    _HEALTH_WORD_RE = re.compile(r"\s+")

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int | None = None,
        context_window_tokens: int | None = None,
        context_block_limit: int | None = None,
        max_tool_result_chars: int | None = None,
        provider_retry_mode: str = "standard",
        web_config: WebToolsConfig | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
        timezone: str | None = None,
        hooks: list[AgentHook] | None = None,
        runtime_config: Config | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig, WebToolsConfig

        defaults = AgentDefaults()
        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.runtime_config = runtime_config.model_copy(deep=True) if runtime_config is not None else None
        self.max_iterations = (
            max_iterations if max_iterations is not None else defaults.max_tool_iterations
        )
        self.context_window_tokens = (
            context_window_tokens
            if context_window_tokens is not None
            else defaults.context_window_tokens
        )
        self.context_block_limit = context_block_limit
        self.max_tool_result_chars = (
            max_tool_result_chars
            if max_tool_result_chars is not None
            else defaults.max_tool_result_chars
        )
        self.provider_retry_mode = provider_retry_mode
        self.web_config = web_config or WebToolsConfig()
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self._start_time = time.time()
        self._last_usage: dict[str, int] = {}
        self._extra_hooks: list[AgentHook] = hooks or []

        self.context = ContextBuilder(workspace, timezone=timezone)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.runner = AgentRunner(provider)
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            web_config=self.web_config,
            max_tool_result_chars=self.max_tool_result_chars,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._background_tasks: list[asyncio.Task] = []
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._provider_cache: dict[tuple[str, str], LLMProvider] = {}
        # NANOBOT_MAX_CONCURRENT_REQUESTS: <=0 means unlimited; default 3.
        _max = int(os.environ.get("NANOBOT_MAX_CONCURRENT_REQUESTS", "3"))
        self._concurrency_gate: asyncio.Semaphore | None = (
            asyncio.Semaphore(_max) if _max > 0 else None
        )
        self.consolidator = Consolidator(
            store=self.context.memory,
            provider=provider,
            model=self.model,
            sessions=self.sessions,
            context_window_tokens=self.context_window_tokens,
            build_messages=self.context.build_messages,
            get_tool_definitions=self.tools.get_definitions,
            max_completion_tokens=provider.generation.max_tokens,
        )
        self.dream = Dream(
            store=self.context.memory,
            provider=provider,
            model=self.model,
            timezone=timezone or defaults.timezone,
        )
        self._register_default_tools()
        self.commands = CommandRouter()
        register_builtin_commands(self.commands)

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if (self.restrict_to_workspace or self.exec_config.sandbox) else None
        extra_read = [BUILTIN_SKILLS_DIR] if allowed_dir else None
        self.tools.register(ReadFileTool(workspace=self.workspace, allowed_dir=allowed_dir, extra_allowed_dirs=extra_read))
        for cls in (WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        for cls in (GlobTool, GrepTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        if self.exec_config.enable:
            self.tools.register(ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
                sandbox=self.exec_config.sandbox,
                path_append=self.exec_config.path_append,
            ))
        if self.web_config.enable:
            self.tools.register(WebSearchTool(config=self.web_config.search, proxy=self.web_config.proxy))
            self.tools.register(WebFetchTool(proxy=self.web_config.proxy))
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if is_health_workspace(self.workspace):
            self.tools.register(SetPreferredNameTool(self.workspace))
            self.tools.register(UpdateHealthProfileTool(self.workspace))
        if self.cron_service:
            self.tools.register(
                CronTool(self.cron_service, default_timezone=self.context.timezone or "UTC")
            )

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from nanobot.agent.tools.mcp import connect_mcp_servers
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except BaseException as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info."""
        for name in ("message", "spawn", "cron"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        from nanobot.utils.helpers import strip_think
        return strip_think(text) or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    @classmethod
    def _normalize_health_user_text(cls, text: str) -> str:
        cleaned = cls._HEALTH_WORD_RE.sub(" ", (text or "").strip().lower())
        return cleaned.strip(" \t\r\n.,;:!?")

    @classmethod
    def _is_trivial_health_opening_text(cls, text: str) -> bool:
        cleaned = cls._normalize_health_user_text(text)
        if cleaned in cls._HEALTH_TRIVIAL_EXACT:
            return True
        if any(cleaned.startswith(prefix) for prefix in cls._HEALTH_TRIVIAL_PREFIXES):
            return True
        return len(cleaned) <= 4

    def _is_health_cold_start(self, session: Session) -> bool:
        if not is_health_workspace(self.workspace):
            return False
        history = session.get_history(max_messages=12)
        user_history = [
            str(message.get("content", ""))
            for message in history
            if message.get("role") == "user"
        ]
        if len(user_history) > 6:
            return False
        return not any(
            not self._is_trivial_health_opening_text(text)
            for text in user_history
        )

    def _health_runtime_context_extra(
        self,
        *,
        temporal=None,
        variation_mode: str | None = None,
        opening_style: str | None = None,
        input_mode: str | None = None,
    ) -> dict[str, str] | None:
        if not is_health_workspace(self.workspace):
            return None
        extra: dict[str, str] = {}
        try:
            preferred_name = HealthWorkspace(self.workspace).load_preferred_name()
        except Exception:
            preferred_name = ""
        if preferred_name:
            extra["Preferred Name"] = preferred_name
        if temporal is not None:
            extra["Local Date"] = temporal.local_date
            extra["Weekday"] = temporal.weekday
            extra["Part Of Day"] = temporal.part_of_day
            extra["Quiet Hours"] = "yes" if temporal.quiet_hours else "no"
            extra["First Touch Today"] = "yes" if temporal.first_touch_today else "no"
            if temporal.days_since_last_user_message is not None:
                extra["Days Since Last User Message"] = str(temporal.days_since_last_user_message)
        if variation_mode:
            extra["Variation Mode"] = variation_mode
        if opening_style:
            extra["Opening Style"] = opening_style
        if input_mode and input_mode != "text":
            extra["Input Mode"] = input_mode
        try:
            wearable_lines = wearable_context_lines(HealthWorkspace(self.workspace))
        except Exception:
            wearable_lines = []
        if wearable_lines:
            extra["Wearable Context"] = " | ".join(wearable_lines)
        return extra or None

    def _refresh_health_timezone(self) -> None:
        if not is_health_workspace(self.workspace):
            return
        try:
            profile = HealthWorkspace(self.workspace).load_profile() or {}
        except Exception:
            profile = {}
        timezone = str(profile.get("timezone") or self.context.timezone or "").strip()
        if not timezone:
            return
        self.context.timezone = timezone
        cron_tool = self.tools.get("cron")
        if isinstance(cron_tool, CronTool):
            cron_tool._default_timezone = timezone

    def _health_lifecycle_overlay(self) -> str | None:
        if not is_health_workspace(self.workspace):
            return None
        memory_md = self.workspace / "memory" / "MEMORY.md"
        try:
            from nanobot.health.chat_workspace import parse_lifecycle_stage

            stage = parse_lifecycle_stage(memory_md)
        except Exception:
            stage = "early"
        try:
            return render_template(
                "health/lifecycle_system.md",
                stage=stage,
                strip=True,
            )
        except Exception:
            return None

    def _build_health_system_prompt(self, session: Session) -> str | None:
        if not is_health_workspace(self.workspace) or not self._is_health_cold_start(session):
            return None
        preferred_name = ""
        try:
            preferred_name = HealthWorkspace(self.workspace).load_preferred_name()
        except Exception:
            preferred_name = ""
        base_prompt = self.context.build_system_prompt()
        cold_start_prompt = render_template(
            "health/cold_start_system.md",
            has_preferred_name=bool(preferred_name),
            preferred_name=preferred_name,
            strip=True,
        )
        return base_prompt + "\n\n---\n\n" + cold_start_prompt

    @staticmethod
    def _health_turn_number(session: Session) -> int:
        return 1 + sum(1 for message in session.messages if message.get("role") == "user")

    @staticmethod
    def _health_recent_session_values(session: Session, key: str, *, limit: int = 3) -> list[str]:
        values = [
            str(message.get(key) or "").strip()
            for message in session.messages
            if message.get("role") == "assistant" and str(message.get(key) or "").strip()
        ]
        return values[-limit:]

    def _annotate_health_response(
        self,
        messages: list[dict[str, Any]],
        *,
        variation_mode: str,
        opening_style: str,
    ) -> None:
        for message in reversed(messages):
            if message.get("role") != "assistant":
                continue
            if message.get("tool_calls"):
                continue
            message["health_variation_mode"] = variation_mode
            message["health_opening_style"] = opening_style
            return

    def _current_provider_name(self) -> str:
        if self.runtime_config is not None:
            return self.runtime_config.get_provider_name(self.model) or "custom"
        return "custom"

    @staticmethod
    def _media_contains_images(media: list[str] | None) -> bool:
        for item in media or []:
            path = Path(item)
            if path.is_file():
                try:
                    mime = detect_image_mime(path.read_bytes()[:64]) or mimetypes.guess_type(path.name)[0]
                except Exception:
                    mime = mimetypes.guess_type(path.name)[0]
            else:
                mime = mimetypes.guess_type(str(path))[0]
            if mime and mime.startswith("image/"):
                return True
        return False

    def _provider_configured(self, provider_name: str) -> bool:
        if self.runtime_config is None:
            return False
        provider_config = getattr(self.runtime_config.providers, provider_name, None)
        if provider_config and provider_config.api_key:
            return True
        spec = find_by_name(provider_name)
        env_key = spec.env_key if spec else ""
        return bool(env_key and os.environ.get(env_key, "").strip())

    def _select_health_model_route(
        self,
        *,
        media: list[str] | None = None,
        force_fallback: bool = False,
    ) -> HealthModelRoute:
        primary_provider = self._current_provider_name()
        primary = HealthModelRoute(
            provider_name=primary_provider,
            model=self.model,
            reason="primary_text",
            fallback_provider_name="openrouter",
            fallback_model="openai/gpt-4o-mini",
        )
        if not is_health_workspace(self.workspace):
            return primary
        if not self._provider_configured("openrouter"):
            return primary
        if force_fallback:
            return HealthModelRoute(
                provider_name="openrouter",
                model="openai/gpt-4o-mini",
                reason="fallback_text",
            )
        if self._media_contains_images(media):
            return HealthModelRoute(
                provider_name="openrouter",
                model="openai/gpt-4o-mini",
                reason="vision_input",
            )
        return primary

    def _provider_for_route(self, route: HealthModelRoute) -> LLMProvider:
        current_provider_name = self._current_provider_name()
        if route.provider_name == current_provider_name and route.model == self.model:
            return self.provider

        cache_key = (route.provider_name, route.model)
        cached = self._provider_cache.get(cache_key)
        if cached is not None:
            return cached
        if self.runtime_config is None:
            return self.provider

        from nanobot.providers.factory import _build_configured_provider

        config = self.runtime_config.model_copy(deep=True)
        config.agents.defaults.provider = route.provider_name
        config.agents.defaults.model = route.model
        provider_config = getattr(config.providers, route.provider_name, None)
        if provider_config is not None and not provider_config.api_key:
            spec = find_by_name(route.provider_name)
            env_key = spec.env_key if spec else ""
            if env_key:
                provider_config.api_key = os.environ.get(env_key, "").strip()
        provider = _build_configured_provider(config, workspace=self.workspace)
        provider.generation = GenerationSettings(
            temperature=self.provider.generation.temperature,
            max_tokens=self.provider.generation.max_tokens,
            reasoning_effort=self.provider.generation.reasoning_effort,
        )
        self._provider_cache[cache_key] = provider
        return provider

    @staticmethod
    def _should_retry_health_route(
        *,
        route: HealthModelRoute | None,
        stop_reason: str,
        tools_used: list[str],
    ) -> bool:
        if route is None:
            return False
        if route.fallback_provider_name is None or route.fallback_model is None:
            return False
        if tools_used:
            return False
        return stop_reason in {"error", "empty_final_response"}

    def _apply_health_continuity(
        self,
        *,
        session: Session,
        content: str,
        metadata: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], Any, str, str]:
        health = HealthWorkspace(self.workspace)
        profile = health.load_profile() or {}
        timezone = str(profile.get("timezone") or self.context.timezone or "UTC").strip() or "UTC"
        temporal = build_temporal_context(
            timezone=timezone,
            last_seen_local_date=str(profile.get("last_seen_local_date") or "").strip() or None,
        )
        is_system_session = session.key.startswith(("heartbeat", "autonomy", "cron:"))
        if is_system_session:
            variation_mode = select_variation_mode(
                user_text=content,
                temporal=temporal,
                recent_modes=self._health_recent_session_values(session, "health_variation_mode"),
            )
            opening_style = select_opening_style(
                temporal=temporal,
                recent_openings=self._health_recent_session_values(session, "health_opening_style"),
                mode=variation_mode,
            )
            return profile, temporal, variation_mode, opening_style

        input_mode = str((metadata or {}).get("input_mode") or "text").strip().lower() or "text"
        facts = extract_health_continuity_facts(content, input_mode=input_mode)

        goals = list(profile.get("goals") or [])
        for goal in facts.goals:
            if goal.lower() not in {item.lower() for item in goals}:
                goals.append(goal)
        profile["goals"] = goals

        friction_points = list(profile.get("friction_points") or [])
        for friction in facts.friction_points:
            if friction.lower() not in {item.lower() for item in friction_points}:
                friction_points.append(friction)
        profile["friction_points"] = friction_points

        communication_preferences = list(profile.get("communication_preferences") or [])
        for pref in facts.communication_preferences:
            if pref.lower() not in {item.lower() for item in communication_preferences}:
                communication_preferences.append(pref)
        profile["communication_preferences"] = communication_preferences

        if facts.open_loop:
            profile["last_open_loop"] = facts.open_loop

        profile_updates: dict[str, Any] = {"last_seen_local_date": temporal.local_date}
        if facts.preferred_name:
            profile_updates["preferred_name"] = facts.preferred_name
        if facts.location:
            profile_updates["location"] = facts.location
        if facts.wake_time:
            profile_updates["wake_time"] = facts.wake_time
        if facts.sleep_time:
            profile_updates["sleep_time"] = facts.sleep_time
        if facts.proactive_enabled is not None:
            profile_updates["proactive_enabled"] = facts.proactive_enabled
        if facts.voice_preferred is not None:
            profile_updates["voice_preferred"] = facts.voice_preferred

        if profile_updates:
            try:
                health.update_profile(**profile_updates)
            except ValueError:
                logger.exception("Failed to persist deterministic health profile updates")
        latest_profile = health.load_profile() or profile
        latest_profile["goals"] = profile["goals"]
        latest_profile["friction_points"] = profile["friction_points"]
        latest_profile["communication_preferences"] = profile["communication_preferences"]
        latest_profile["last_open_loop"] = profile.get(
            "last_open_loop",
            latest_profile.get("last_open_loop", "none"),
        )
        health.save_profile(latest_profile)
        health.refresh_workspace_assets(include_memory=False)
        apply_health_continuity_updates(
            user_md=self.workspace / "USER.md",
            memory_md=self.workspace / "memory" / "MEMORY.md",
            existing_profile=latest_profile,
            temporal=temporal,
            facts=facts,
        )

        variation_mode = select_variation_mode(
            user_text=content,
            temporal=temporal,
            recent_modes=self._health_recent_session_values(session, "health_variation_mode"),
        )
        opening_style = select_opening_style(
            temporal=temporal,
            recent_openings=self._health_recent_session_values(session, "health_opening_style"),
            mode=variation_mode,
        )
        return latest_profile, temporal, variation_mode, opening_style

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        *,
        session: Session | None = None,
        channel: str = "cli",
        chat_id: str = "direct",
        message_id: str | None = None,
        route: HealthModelRoute | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop.

        *on_stream*: called with each content delta during streaming.
        *on_stream_end(resuming)*: called when a streaming session finishes.
        ``resuming=True`` means tool calls follow (spinner should restart);
        ``resuming=False`` means this is the final response.
        """
        loop_hook = _LoopHook(
            self,
            on_progress=on_progress,
            on_stream=on_stream,
            on_stream_end=on_stream_end,
            channel=channel,
            chat_id=chat_id,
            message_id=message_id,
        )
        hook: AgentHook = (
            _LoopHookChain(loop_hook, self._extra_hooks)
            if self._extra_hooks
            else loop_hook
        )

        async def _checkpoint(payload: dict[str, Any]) -> None:
            if session is None:
                return
            self._set_runtime_checkpoint(session, payload)

        selected_route = route or HealthModelRoute(
            provider_name=self._current_provider_name(),
            model=self.model,
            reason="default",
        )
        runner_provider = self._provider_for_route(selected_route)
        runner = self.runner if runner_provider is self.provider else AgentRunner(runner_provider)

        result = await runner.run(AgentRunSpec(
            initial_messages=initial_messages,
            tools=self.tools,
            model=selected_route.model,
            max_iterations=self.max_iterations,
            max_tool_result_chars=self.max_tool_result_chars,
            hook=hook,
            error_message="Sorry, I encountered an error calling the AI model.",
            concurrent_tools=True,
            workspace=self.workspace,
            session_key=session.key if session else None,
            context_window_tokens=self.context_window_tokens,
            context_block_limit=self.context_block_limit,
            provider_retry_mode=self.provider_retry_mode,
            progress_callback=on_progress,
            checkpoint_callback=_checkpoint,
        ))
        if self._should_retry_health_route(
            route=selected_route,
            stop_reason=result.stop_reason,
            tools_used=result.tools_used,
        ):
            fallback_route = HealthModelRoute(
                provider_name=selected_route.fallback_provider_name or selected_route.provider_name,
                model=selected_route.fallback_model or selected_route.model,
                reason="fallback_text",
            )
            logger.warning(
                "Retrying health turn with fallback route {}:{} after {}",
                fallback_route.provider_name,
                fallback_route.model,
                result.stop_reason,
            )
            fallback_provider = self._provider_for_route(fallback_route)
            fallback_runner = (
                self.runner if fallback_provider is self.provider else AgentRunner(fallback_provider)
            )
            result = await fallback_runner.run(AgentRunSpec(
                initial_messages=initial_messages,
                tools=self.tools,
                model=fallback_route.model,
                max_iterations=self.max_iterations,
                max_tool_result_chars=self.max_tool_result_chars,
                hook=hook,
                error_message="Sorry, I encountered an error calling the AI model.",
                concurrent_tools=True,
                workspace=self.workspace,
                session_key=session.key if session else None,
                context_window_tokens=self.context_window_tokens,
                context_block_limit=self.context_block_limit,
                provider_retry_mode=self.provider_retry_mode,
                progress_callback=on_progress,
                checkpoint_callback=_checkpoint,
            ))
        self._last_usage = result.usage
        if result.stop_reason == "max_iterations":
            logger.warning("Max iterations ({}) reached", self.max_iterations)
        elif result.stop_reason == "error":
            logger.error("LLM returned error: {}", (result.final_content or "")[:200])
        return result.final_content, result.tools_used, result.messages

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                # Preserve real task cancellation so shutdown can complete cleanly.
                # Only ignore non-task CancelledError signals that may leak from integrations.
                if not self._running or asyncio.current_task().cancelling():
                    raise
                continue
            except Exception as e:
                logger.warning("Error consuming inbound message: {}, continuing...", e)
                continue

            raw = msg.content.strip()
            if self.commands.is_priority(raw):
                ctx = CommandContext(msg=msg, session=None, key=msg.session_key, raw=raw, loop=self)
                result = await self.commands.dispatch_priority(ctx)
                if result:
                    await self.bus.publish_outbound(result)
                continue
            task = asyncio.create_task(self._dispatch(msg))
            self._active_tasks.setdefault(msg.session_key, []).append(task)
            task.add_done_callback(lambda t, k=msg.session_key: self._active_tasks.get(k, []) and self._active_tasks[k].remove(t) if t in self._active_tasks.get(k, []) else None)

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message: per-session serial, cross-session concurrent."""
        lock = self._session_locks.setdefault(msg.session_key, asyncio.Lock())
        gate = self._concurrency_gate or nullcontext()
        async with lock, gate:
            try:
                on_stream = on_stream_end = None
                if msg.metadata.get("_wants_stream"):
                    # Split one answer into distinct stream segments.
                    stream_base_id = f"{msg.session_key}:{time.time_ns()}"
                    stream_segment = 0

                    def _current_stream_id() -> str:
                        return f"{stream_base_id}:{stream_segment}"

                    async def on_stream(delta: str) -> None:
                        meta = dict(msg.metadata or {})
                        meta["_stream_delta"] = True
                        meta["_stream_id"] = _current_stream_id()
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel, chat_id=msg.chat_id,
                            content=delta,
                            metadata=meta,
                        ))

                    async def on_stream_end(*, resuming: bool = False) -> None:
                        nonlocal stream_segment
                        meta = dict(msg.metadata or {})
                        meta["_stream_end"] = True
                        meta["_resuming"] = resuming
                        meta["_stream_id"] = _current_stream_id()
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel, chat_id=msg.chat_id,
                            content="",
                            metadata=meta,
                        ))
                        stream_segment += 1

                response = await self._process_message(
                    msg, on_stream=on_stream, on_stream_end=on_stream_end,
                )
                if response is not None:
                    await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content="", metadata=msg.metadata or {},
                    ))
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Sorry, I encountered an error.",
                ))

    async def close_mcp(self) -> None:
        """Drain pending background archives, then close MCP connections."""
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def _schedule_background(self, coro) -> None:
        """Schedule a coroutine as a tracked background task (drained on shutdown)."""
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)
        task.add_done_callback(self._background_tasks.remove)

    async def _post_turn_maintenance(self, session: Session) -> None:
        """Second-pass consolidation and optional session file compaction."""
        await self.consolidator.maybe_consolidate_by_tokens(session)
        self.sessions.compact_session_file(session)

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            if self._restore_runtime_checkpoint(session):
                self.sessions.save(session)
            await self.consolidator.maybe_consolidate_by_tokens(session)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
            history = session.get_history(max_messages=0)
            current_role = "assistant" if msg.sender_id == "subagent" else "user"
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content, channel=channel, chat_id=chat_id,
                current_role=current_role,
            )
            final_content, _, all_msgs = await self._run_agent_loop(
                messages, session=session, channel=channel, chat_id=chat_id,
                message_id=msg.metadata.get("message_id"),
            )
            self._save_turn(session, all_msgs, 1 + len(history))
            self._clear_runtime_checkpoint(session)
            self.sessions.save(session)
            self._schedule_background(self._post_turn_maintenance(session))
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)
        is_internal_turn = bool((msg.metadata or {}).get("_internal"))
        if self._restore_runtime_checkpoint(session):
            self.sessions.save(session)

        # Slash commands
        raw = msg.content.strip()
        ctx = CommandContext(msg=msg, session=session, key=key, raw=raw, loop=self)
        if result := await self.commands.dispatch(ctx):
            return result

        if (
            health_distribution_enabled(self.workspace)
            and not is_health_workspace(self.workspace)
            and msg.channel in {"telegram", "whatsapp"}
            and not raw.startswith("/")
        ):
            health = HealthWorkspace(self.workspace)
            setup = health.load_setup()
            if setup and health.validate_setup_token(setup.get("token", "")):
                url = health.setup_url(setup["token"])
                message = (
                    "Before we chat, please finish setting up your health assistant:\n\n"
                    f"{url}"
                )
            else:
                token, _ = health.get_or_create_invite(channel=msg.channel, chat_id=msg.chat_id)
                message = (
                    "Before we chat, please finish the health onboarding form:\n\n"
                    f"{health.onboarding_url(token)}"
                )
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=message,
                metadata={**dict(msg.metadata or {}), "render_as": "text"},
            )

        if is_health_workspace(self.workspace):
            try:
                health_workspace = HealthWorkspace(self.workspace)
                if msg.channel in {"telegram", "whatsapp"}:
                    health_workspace.bind_chat_session(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                    )
                if not is_internal_turn and not key.startswith(("heartbeat", "autonomy", "cron:")):
                    health_workspace.record_user_activity()
            except Exception:
                pass

        if not is_internal_turn and is_health_workspace(self.workspace) and is_emergency_language(msg.content):
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=emergency_response(),
                metadata={**dict(msg.metadata or {}), "render_as": "text"},
            )

        onboarding = (
            (self.workspace / ".health_chat_onboarding").exists()
            and msg.channel in {"telegram", "whatsapp"}
        )
        tools_backup = self.tools
        if onboarding:
            self.tools = ToolRegistry()
            self.tools.register(
                CompleteOnboardingTool(
                    self.workspace,
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    user_token=read_tenant_user_token(self.workspace),
                )
            )
        try:
            await self.consolidator.maybe_consolidate_by_tokens(session)
            self._refresh_health_timezone()
            health_temporal = None
            variation_mode = None
            opening_style = None
            if is_health_workspace(self.workspace) and not onboarding and not is_internal_turn:
                _, health_temporal, variation_mode, opening_style = self._apply_health_continuity(
                    session=session,
                    content=msg.content,
                    metadata=msg.metadata,
                )
                self._refresh_health_timezone()

            if not onboarding and not is_internal_turn:
                self.context.memory.record_user_activity(timezone=self.context.timezone)
                self.context.memory.capture_interest_signals(
                    msg.content,
                    timezone=self.context.timezone,
                )

            self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
            if message_tool := self.tools.get("message"):
                if isinstance(message_tool, MessageTool):
                    message_tool.start_turn()

            history = session.get_history(max_messages=0)
            onboarding_prompt = (
                render_template("health/onboarding_system.md", strip=True) if onboarding else None
            )
            input_mode = str(msg.metadata.get("input_mode") or "text").strip().lower() or "text"
            runtime_context_extra = self._health_runtime_context_extra(
                temporal=health_temporal,
                variation_mode=variation_mode,
                opening_style=opening_style,
                input_mode=input_mode,
            )
            route = (
                self._select_health_model_route(media=msg.media if msg.media else None)
                if is_health_workspace(self.workspace) and not onboarding
                else None
            )
            system_prompt = onboarding_prompt or self._build_health_system_prompt(session)
            if system_prompt is None:
                system_prompt = self.context.build_system_prompt()
            if is_health_workspace(self.workspace) and not onboarding_prompt:
                life = self._health_lifecycle_overlay()
                if life:
                    system_prompt = f"{system_prompt}\n\n---\n\n{life}"
                if health_temporal is not None and variation_mode and opening_style:
                    system_prompt = (
                        f"{system_prompt}\n\n---\n\n"
                        + build_health_behavior_overlay(
                            temporal=health_temporal,
                            mode=variation_mode,
                            opening_style=opening_style,
                            turn_number=self._health_turn_number(session),
                            input_mode=input_mode,
                        )
                    )
            initial_messages = self.context.build_messages(
                history=history,
                current_message=msg.content,
                media=msg.media if msg.media else None,
                channel=msg.channel, chat_id=msg.chat_id,
                system_prompt=system_prompt,
                runtime_context_extra=runtime_context_extra,
            )

            async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
                meta = dict(msg.metadata or {})
                meta["_progress"] = True
                meta["_tool_hint"] = tool_hint
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
                    visibility="internal",
                ))

            final_content, _, all_msgs = await self._run_agent_loop(
                initial_messages,
                on_progress=on_progress or _bus_progress,
                on_stream=on_stream,
                on_stream_end=on_stream_end,
                session=session,
                channel=msg.channel, chat_id=msg.chat_id,
                message_id=msg.metadata.get("message_id"),
                route=route,
            )

            if final_content is None or not final_content.strip():
                final_content = EMPTY_FINAL_RESPONSE_MESSAGE

            if variation_mode and opening_style:
                self._annotate_health_response(
                    all_msgs,
                    variation_mode=variation_mode,
                    opening_style=opening_style,
                )
            if is_internal_turn:
                if bool((msg.metadata or {}).get("_persist_internal_response", True)):
                    self._save_internal_response(session, all_msgs)
            else:
                self._save_turn(session, all_msgs, 1 + len(history))
            self._clear_runtime_checkpoint(session)
            self.sessions.save(session)
            self._schedule_background(self._post_turn_maintenance(session))

            if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
                return None

            preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
            logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)

            meta = dict(msg.metadata or {})
            if on_stream is not None:
                meta["_streamed"] = True
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=final_content,
                metadata=meta,
            )
        finally:
            if onboarding:
                self.tools = tools_backup

    def _sanitize_persisted_blocks(
        self,
        content: list[dict[str, Any]],
        *,
        truncate_text: bool = False,
        drop_runtime: bool = False,
    ) -> list[dict[str, Any]]:
        """Strip volatile multimodal payloads before writing session history."""
        filtered: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                filtered.append(block)
                continue

            if (
                drop_runtime
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
                and block["text"].startswith(ContextBuilder._RUNTIME_CONTEXT_TAG)
            ):
                continue

            if (
                block.get("type") == "image_url"
                and block.get("image_url", {}).get("url", "").startswith("data:image/")
            ):
                path = (block.get("_meta") or {}).get("path", "")
                filtered.append({"type": "text", "text": image_placeholder_text(path)})
                continue

            if block.get("type") == "text" and isinstance(block.get("text"), str):
                text = block["text"]
                if truncate_text and len(text) > self.max_tool_result_chars:
                    text = truncate_text(text, self.max_tool_result_chars)
                filtered.append({**block, "text": text})
                continue

            filtered.append(block)

        return filtered

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime
        for m in messages[skip:]:
            entry = dict(m)
            entry.pop("reasoning_content", None)
            entry.pop("thinking_blocks", None)
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and isinstance(content, str):
                stripped = self._strip_think(content)
                if not stripped and not entry.get("tool_calls"):
                    continue
                entry["content"] = stripped
                content = entry["content"]
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # skip empty assistant messages — they poison session context
            if role == "tool":
                if isinstance(content, str) and len(content) > self.max_tool_result_chars:
                    entry["content"] = truncate_text(content, self.max_tool_result_chars)
                elif isinstance(content, list):
                    filtered = self._sanitize_persisted_blocks(content, truncate_text=True)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            elif role == "user":
                if isinstance(content, str) and content.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                    # Strip the runtime-context prefix, keep only the user text.
                    parts = content.split("\n\n", 1)
                    if len(parts) > 1 and parts[1].strip():
                        entry["content"] = parts[1]
                    else:
                        continue
                if isinstance(content, list):
                    filtered = self._sanitize_persisted_blocks(content, drop_runtime=True)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    def _save_internal_response(self, session: Session, messages: list[dict[str, Any]]) -> None:
        from datetime import datetime

        for message in reversed(messages):
            if message.get("role") != "assistant" or message.get("tool_calls"):
                continue
            entry = dict(message)
            entry.pop("reasoning_content", None)
            entry.pop("thinking_blocks", None)
            content = self._strip_think(entry.get("content"))
            if not content:
                return
            entry["content"] = content
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
            session.updated_at = datetime.now()
            return

    def _set_runtime_checkpoint(self, session: Session, payload: dict[str, Any]) -> None:
        """Persist the latest in-flight turn state into session metadata."""
        cleaned = dict(payload)
        if isinstance(cleaned.get("assistant_message"), dict):
            cleaned["assistant_message"] = dict(cleaned["assistant_message"])
            cleaned["assistant_message"].pop("reasoning_content", None)
            cleaned["assistant_message"].pop("thinking_blocks", None)
            assistant_content = cleaned["assistant_message"].get("content")
            if isinstance(assistant_content, str):
                cleaned["assistant_message"]["content"] = self._strip_think(assistant_content)
        completed_tool_results = []
        for message in cleaned.get("completed_tool_results") or []:
            if isinstance(message, dict):
                stripped = dict(message)
                stripped.pop("reasoning_content", None)
                stripped.pop("thinking_blocks", None)
                completed_tool_results.append(stripped)
        cleaned["completed_tool_results"] = completed_tool_results
        session.metadata[self._RUNTIME_CHECKPOINT_KEY] = cleaned
        if hasattr(self, "sessions"):
            self.sessions.save(session)

    def _clear_runtime_checkpoint(self, session: Session) -> None:
        if self._RUNTIME_CHECKPOINT_KEY in session.metadata:
            session.metadata.pop(self._RUNTIME_CHECKPOINT_KEY, None)

    @staticmethod
    def _checkpoint_message_key(message: dict[str, Any]) -> tuple[Any, ...]:
        return (
            message.get("role"),
            message.get("content"),
            message.get("tool_call_id"),
            message.get("name"),
            message.get("tool_calls"),
        )

    def _restore_runtime_checkpoint(self, session: Session) -> bool:
        """Materialize an unfinished turn into session history before a new request."""
        from datetime import datetime

        checkpoint = session.metadata.get(self._RUNTIME_CHECKPOINT_KEY)
        if not isinstance(checkpoint, dict):
            return False

        assistant_message = checkpoint.get("assistant_message")
        completed_tool_results = checkpoint.get("completed_tool_results") or []
        pending_tool_calls = checkpoint.get("pending_tool_calls") or []

        restored_messages: list[dict[str, Any]] = []
        if isinstance(assistant_message, dict):
            restored = dict(assistant_message)
            restored.setdefault("timestamp", datetime.now().isoformat())
            restored_messages.append(restored)
        for message in completed_tool_results:
            if isinstance(message, dict):
                restored = dict(message)
                restored.setdefault("timestamp", datetime.now().isoformat())
                restored_messages.append(restored)
        for tool_call in pending_tool_calls:
            if not isinstance(tool_call, dict):
                continue
            tool_id = tool_call.get("id")
            name = ((tool_call.get("function") or {}).get("name")) or "tool"
            restored_messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "name": name,
                "content": "Error: Task interrupted before this tool finished.",
                "timestamp": datetime.now().isoformat(),
            })

        overlap = 0
        max_overlap = min(len(session.messages), len(restored_messages))
        for size in range(max_overlap, 0, -1):
            existing = session.messages[-size:]
            restored = restored_messages[:size]
            if all(
                self._checkpoint_message_key(left) == self._checkpoint_message_key(right)
                for left, right in zip(existing, restored)
            ):
                overlap = size
                break
        session.messages.extend(restored_messages[overlap:])

        self._clear_runtime_checkpoint(session)
        return True

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a message directly and return the outbound payload."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        return await self._process_message(
            msg, session_key=session_key, on_progress=on_progress,
            on_stream=on_stream, on_stream_end=on_stream_end,
        )

    async def process_internal(
        self,
        content: str,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_stream: Callable[[str], Awaitable[None]] | None = None,
        on_stream_end: Callable[..., Awaitable[None]] | None = None,
        persist_response: bool = True,
    ) -> OutboundMessage | None:
        """Process a hidden system-initiated turn against a real user session."""
        await self._connect_mcp()
        msg = InboundMessage(
            channel=channel,
            sender_id="system",
            chat_id=chat_id,
            content="[Internal Turn — system instruction, not user text]\n\n" + content,
            metadata={
                "_internal": True,
                "_persist_internal_response": persist_response,
            },
        )
        return await self._process_message(
            msg,
            session_key=session_key,
            on_progress=on_progress,
            on_stream=on_stream,
            on_stream_end=on_stream_end,
        )
