from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.config.loader import load_config
from nanobot.executor.turn import TurnExecutor, TurnExecutorDeps
from nanobot.nanobot import _make_provider
from nanobot.store.locks import RedisDistributedLock, RedisLockConfig, lock
from nanobot.store.memory_mem0 import Mem0MemoryRepository
from nanobot.store.postgres import (
    PostgresCheckpointRepository,
    PostgresMemoryRepository,
    PostgresPool,
    PostgresSessionRepository,
    PostgresStoreConfig,
    ensure_tenant_id,
)
from nanobot.worker.stream import RedisStreamConfig, RedisStreamHook
from nanobot.observability.langfuse import LangfuseTracer, load_langfuse_config
from nanobot.observability.metrics import agent_turn_duration_seconds, agent_turns_total


@dataclass(slots=True)
class WorkerContext:
    config: Any
    pg_pool_mgr: PostgresPool
    lock_mgr: RedisDistributedLock


async def startup(ctx: dict[str, Any]) -> None:
    config = load_config(None)
    if not config.store.database_url:
        raise RuntimeError("config.store.database_url is required for platform worker")

    pg_pool_mgr = PostgresPool(PostgresStoreConfig(database_url=config.store.database_url))
    await pg_pool_mgr.init()
    lock_mgr = RedisDistributedLock(RedisLockConfig(redis_url=config.store.redis_url))
    ctx["worker"] = WorkerContext(config=config, pg_pool_mgr=pg_pool_mgr, lock_mgr=lock_mgr)


async def shutdown(ctx: dict[str, Any]) -> None:
    w: WorkerContext | None = ctx.get("worker")
    if w:
        await w.pg_pool_mgr.close()


async def process_turn(
    ctx: dict[str, Any],
    *,
    request_id: str,
    tenant_external_id: str,
    session_key: str,
    channel: str,
    chat_id: str,
    content: str,
) -> dict[str, Any]:
    w: WorkerContext = ctx["worker"]
    config = w.config

    provider = _make_provider(config)
    pool = await w.pg_pool_mgr.init()
    tenant_id = await ensure_tenant_id(pool, tenant_external_id)

    session_repo = PostgresSessionRepository(pool)
    memory_docs = PostgresMemoryRepository(pool)
    memory_repo = (
        Mem0MemoryRepository(documents=memory_docs, mem0_config=config.store.mem0_config)
        if config.store.mem0_config is not None
        else memory_docs
    )
    checkpoint_repo = PostgresCheckpointRepository(pool)

    lock_name = f"{tenant_id}:{session_key}"
    started = time.time()
    status = "ok"
    async with lock(w.lock_mgr, lock_name, ttl_s=180, wait_s=10):
        executor = TurnExecutor(
            TurnExecutorDeps(
                config=config,
                provider=provider,
                session_repo=session_repo,
                memory_repo=memory_repo,
                checkpoint_repo=checkpoint_repo,
            )
        )
        hook = RedisStreamHook(cfg=RedisStreamConfig(redis_url=config.store.redis_url), request_id=request_id)
        try:
            outbound = await executor.execute(
                tenant_id=tenant_id,
                message=InboundMessage(
                    channel=channel,
                    sender_id=tenant_external_id,
                    chat_id=chat_id,
                    content=content,
                ),
                hook=hook,
            )
        except Exception:
            status = "error"
            raise
        finally:
            dur = max(0.0, time.time() - started)
            agent_turn_duration_seconds.labels(channel=channel).observe(dur)
            agent_turns_total.labels(status=status, channel=channel).inc()

            lf_cfg = load_langfuse_config()
            if lf_cfg:
                LangfuseTracer(lf_cfg).trace_turn(
                    name="process_turn",
                    tenant_id=tenant_id,
                    session_key=session_key,
                    channel=channel,
                    model=config.agents.defaults.model,
                    input_text=content,
                    output_text=getattr(outbound, "content", "") if status == "ok" else "",
                    duration_s=dur,
                    status=status,
                )

        return {"request_id": request_id, "content": outbound.content}


class WorkerSettings:
    functions = [process_turn]
    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings.from_dsn(os.environ.get("ARQ_REDIS_URL", "redis://localhost:6379/0"))

