from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from loguru import logger

from nanobot.agent.runner import AgentRunSpec, AgentRunner
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.search import GlobTool, GrepTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.config.schema import Config
from nanobot.health.storage import is_health_workspace
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session
from nanobot.store.base import CheckpointRepository, MemoryRepository, SessionRepository
from nanobot.agent.subagent import SubagentManager
from nanobot.utils.helpers import build_assistant_message
from nanobot.agent.context import ContextBuilder


@dataclass(slots=True)
class TurnExecutorDeps:
    config: Config
    provider: LLMProvider
    session_repo: SessionRepository
    memory_repo: MemoryRepository
    checkpoint_repo: CheckpointRepository | None = None
    workspace_root: Path | None = None
    send_callback: Callable[[OutboundMessage], Any] | None = None


class TurnExecutor:
    """Stateless single-turn execution.

    Loads session + memory from repositories, runs the existing AgentRunner tool loop,
    then persists the updated session and any checkpoints.
    """

    def __init__(self, deps: TurnExecutorDeps):
        self._deps = deps
        self._runner = AgentRunner(deps.provider)

    def _workspace_for(self, tenant_id: str) -> Path:
        root = self._deps.workspace_root or Path("~/.nanobot/platform-workspaces").expanduser()
        return (root / str(tenant_id)).resolve()

    async def _build_system_prompt(self, tenant_id: str, workspace: Path) -> str:
        ctx = ContextBuilder(workspace, timezone=self._deps.config.agents.defaults.timezone)
        return await ctx.build_system_prompt_from_repo(
            tenant_id=tenant_id,
            memory_repo=self._deps.memory_repo,
        )

    def _build_tools(self, workspace: Path) -> ToolRegistry:
        cfg = self._deps.config
        tools = ToolRegistry()

        allowed_dir = workspace if (cfg.tools.restrict_to_workspace or cfg.tools.exec.sandbox) else None
        tools.register(ReadFileTool(workspace=workspace, allowed_dir=allowed_dir))
        for cls in (WriteFileTool, EditFileTool, ListDirTool):
            tools.register(cls(workspace=workspace, allowed_dir=allowed_dir))
        for cls in (GlobTool, GrepTool):
            tools.register(cls(workspace=workspace, allowed_dir=allowed_dir))

        if cfg.tools.exec.enable:
            tools.register(
                ExecTool(
                    working_dir=str(workspace),
                    timeout=cfg.tools.exec.timeout,
                    restrict_to_workspace=cfg.tools.restrict_to_workspace,
                    sandbox=cfg.tools.exec.sandbox,
                    path_append=cfg.tools.exec.path_append,
                )
            )

        if cfg.tools.web.enable:
            tools.register(WebSearchTool(config=cfg.tools.web.search, proxy=cfg.tools.web.proxy))
            tools.register(WebFetchTool(proxy=cfg.tools.web.proxy))

        if self._deps.send_callback is not None:
            tools.register(MessageTool(send_callback=self._deps.send_callback))

        # Subagents require a workspace to operate; we allow it for now (platform hardening later).
        subagents = SubagentManager(
            provider=self._deps.provider,
            workspace=workspace,
            bus=MessageBus(),  # isolated; platform mode will route via queue instead
            web_config=cfg.tools.web,
            max_tool_result_chars=cfg.agents.defaults.max_tool_result_chars,
            model=cfg.agents.defaults.model,
            exec_config=cfg.tools.exec,
            restrict_to_workspace=cfg.tools.restrict_to_workspace,
        )
        tools.register(SpawnTool(manager=subagents))

        return tools

    async def execute(
        self,
        *,
        tenant_id: str,
        message: InboundMessage,
        hook: Any | None = None,
    ) -> OutboundMessage:
        cfg = self._deps.config
        workspace = self._workspace_for(tenant_id)
        workspace.mkdir(parents=True, exist_ok=True)

        session_key = message.session_key
        session: Session = await self._deps.session_repo.get(tenant_id, session_key)

        history = session.get_history()
        system_prompt = await self._build_system_prompt(tenant_id, workspace)
        messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": message.content}]

        tools = self._build_tools(workspace)

        run_spec = AgentRunSpec(
            initial_messages=messages,
            tools=tools,
            model=cfg.agents.defaults.model,
            max_iterations=cfg.agents.defaults.max_tool_iterations,
            max_tool_result_chars=cfg.agents.defaults.max_tool_result_chars,
            temperature=cfg.agents.defaults.temperature,
            max_tokens=cfg.agents.defaults.max_tokens,
            reasoning_effort=cfg.agents.defaults.reasoning_effort,
            hook=hook,
            workspace=workspace,
            session_key=session_key,
            context_window_tokens=cfg.agents.defaults.context_window_tokens,
            context_block_limit=cfg.agents.defaults.context_block_limit,
            provider_retry_mode=cfg.agents.defaults.provider_retry_mode,
        )

        try:
            result = await self._runner.run(run_spec)
        except Exception:
            logger.exception("TurnExecutor failed")
            content = "Sorry, I hit an internal error."
            session.messages.append({"role": "assistant", "content": content})
            await self._deps.session_repo.save(tenant_id, session)
            return OutboundMessage(channel=message.channel, chat_id=message.chat_id, content=content, reply_to=None)

        # Persist: append the new assistant message to session.
        final_text = (getattr(result, "final_content", None) or "").strip()
        session.messages.append({"role": "user", "content": message.content})
        session.messages.append(build_assistant_message(final_text))
        await self._deps.session_repo.save(tenant_id, session)

        return OutboundMessage(channel=message.channel, chat_id=message.chat_id, content=final_text, reply_to=None)

