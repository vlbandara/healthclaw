from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from croniter import croniter
from arq import cron
from arq.connections import RedisSettings
from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.config.loader import load_config
from nanobot.executor.turn import TurnExecutor, TurnExecutorDeps
from nanobot.nanobot import _make_provider
from nanobot.providers.base import LLMProvider, LLMResponse
from nanobot.store.locks import RedisDistributedLock, RedisLockConfig, lock
from nanobot.store.memory_mem0 import Mem0MemoryRepository
from nanobot.store.onboarding import PostgresOnboardingRepository
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


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _compute_next_run(schedule: str, *, tz: str) -> datetime:
    from zoneinfo import ZoneInfo

    base = datetime.now(ZoneInfo(tz))
    itr = croniter(schedule, base)
    nxt = itr.get_next(datetime)
    if nxt.tzinfo is None:
        nxt = nxt.replace(tzinfo=ZoneInfo(tz))
    return nxt.astimezone(UTC)


async def _send_telegram(*, bot_token: str, chat_id: str, text: str) -> None:
    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required for proactive Telegram sends")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(url, json={"chat_id": chat_id, "text": text})
        res.raise_for_status()


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
                onboarding_repo=PostgresOnboardingRepository(pool),
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


async def cron_tick(ctx: dict[str, Any]) -> None:
    """Run due cron jobs and deliver proactive messages."""
    w: WorkerContext = ctx["worker"]
    config = w.config
    pool = await w.pg_pool_mgr.init()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        # No-op if not configured (e.g., API-only deployments).
        return

    due = []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, tenant_id, schedule, payload
            FROM cron_jobs
            WHERE enabled = true AND next_run_at <= now()
            ORDER BY next_run_at ASC
            LIMIT 25
            """
        )
        due = list(rows)

    if not due:
        return

    provider = _make_provider(config)
    session_repo = PostgresSessionRepository(pool)
    memory_docs = PostgresMemoryRepository(pool)
    memory_repo = (
        Mem0MemoryRepository(documents=memory_docs, mem0_config=config.store.mem0_config)
        if config.store.mem0_config is not None
        else memory_docs
    )
    checkpoint_repo = PostgresCheckpointRepository(pool)
    onboarding_repo = PostgresOnboardingRepository(pool)

    executor = TurnExecutor(
        TurnExecutorDeps(
            config=config,
            provider=provider,
            session_repo=session_repo,
            memory_repo=memory_repo,
            onboarding_repo=onboarding_repo,
            checkpoint_repo=checkpoint_repo,
        )
    )

    for row in due:
        job_id = str(row["id"])
        tenant_id = str(row["tenant_id"])
        schedule = str(row["schedule"] or "").strip()
        payload = row["payload"] or {}
        if isinstance(payload, str):
            try:
                import json as _json

                payload = _json.loads(payload)
            except Exception:
                payload = {}

        kind = str((payload or {}).get("kind") or "").strip()
        channel = str((payload or {}).get("channel") or "telegram").strip()
        chat_id = str((payload or {}).get("chat_id") or "").strip()
        tz = str((payload or {}).get("tz") or "UTC").strip() or "UTC"
        if channel != "telegram" or not chat_id or not schedule:
            continue

        # Compute next run first to avoid double-sends on crashes.
        try:
            next_run_at = _compute_next_run(schedule, tz=tz)
        except Exception:
            next_run_at = _utcnow()

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE cron_jobs
                SET next_run_at = $2, last_run_at = now()
                WHERE id = $1::uuid
                """,
                job_id,
                next_run_at,
            )

        prompt = (
            "Send a short morning check-in. One clear next step, one grounded question."
            if kind == "morning_check_in"
            else "Send a short weekly reset: one pattern you noticed, one small adjustment, one question."
        )
        outbound = await executor.execute(
            tenant_id=tenant_id,
            message=InboundMessage(
                channel="telegram",
                sender_id=f"telegram:{chat_id}",
                chat_id=chat_id,
                content=prompt,
            ),
        )
        if outbound and outbound.content:
            try:
                await _send_telegram(bot_token=bot_token, chat_id=chat_id, text=outbound.content)
            except Exception:
                logger.exception("cron_tick telegram send failed")


class WorkerSettings:
    functions = [process_turn, cron_tick]
    on_startup = startup
    on_shutdown = shutdown

    redis_settings = RedisSettings.from_dsn(os.environ.get("ARQ_REDIS_URL", "redis://localhost:6379/0"))

    cron_jobs = [
        cron(cron_tick, minute=set(range(60))),
    ]

