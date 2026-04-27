from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from arq import Worker
from arq.connections import RedisSettings

from nanobot.health.api import (
    _apply_setup_channel_config,
    _build_setup_spawn_env,
    _submission_with_wearables_seed,
    _configure_logging,
    _load_health_instance_config_template,
    _setup_status_payload,
)
from nanobot.health.bootstrap import persist_health_onboarding
from nanobot.health.metrics import spawn_attempts, spawn_failures, spawn_success
from nanobot.health.registry import HealthRegistry
from nanobot.health.spawner import HealthInstanceSpawner
from nanobot.health.storage import HealthWorkspace, get_health_vault_secret

logger = logging.getLogger("nanobot.health.worker")


def _resolve_workspace_root() -> Path:
    raw = os.environ.get("NANOBOT_WORKSPACE") or "~/.nanobot/workspace"
    return Path(raw).expanduser().resolve()


def _staging_root(workspace_root: Path) -> Path:
    return workspace_root / "health-staging"


def _health_for_setup_token(workspace_root: Path, setup_token: str) -> HealthWorkspace:
    root = _staging_root(workspace_root)
    root.mkdir(parents=True, exist_ok=True)
    session_dir = root / setup_token
    session_dir.mkdir(parents=True, exist_ok=True)
    return HealthWorkspace(session_dir)


async def spawn_instance_job(ctx: dict[str, Any], setup_token: str) -> dict[str, Any]:
    """Provision a per-user gateway container for a setup token."""
    workspace_root = _resolve_workspace_root()
    health_secret = get_health_vault_secret()

    health = _health_for_setup_token(workspace_root, setup_token)
    setup = health.validate_setup_token(setup_token)
    if not setup:
        raise RuntimeError("Setup session not found or expired.")

    submission = health.load_profile_draft_submission(secret=health_secret)
    if not submission:
        # Minimal onboarding fallback.
        profile = setup.get("profile") or {}
        phase1 = profile.get("phase1") or {}
        phase2 = profile.get("phase2") or {}
        submission = {"phase1": dict(phase1), "phase2": dict(phase2)}
    submission = _submission_with_wearables_seed(
        submission,
        health=health,
        secret=health_secret,
    )

    payload = _setup_status_payload(
        health,
        secret=health_secret,
        fallback_links={},
        bridge_snapshot=None,
    )
    telegram_token = (health.load_setup_secrets(secret=health_secret).get("telegram", {}) or {}).get(
        "bot_token", ""
    )
    if not any(bool(item.get("connected")) for item in payload["channels"].values() if isinstance(item, dict)):
        raise RuntimeError("No connected channel available for activation.")

    # Ensure health profile exists on workspace_root (shared) for audit/debug.
    persist_health_onboarding(
        workspace_root,
        submission,
        invite=None,
        secret=health_secret,
        stable_token_hint=setup_token,
    )

    config_json = _apply_setup_channel_config(
        _load_health_instance_config_template(),
        channels_payload=payload["channels"],
    )
    try:
        config_json.setdefault("agents", {}).setdefault("defaults", {})["timezone"] = (
            submission.get("phase1", {}) or {}
        ).get("timezone", "UTC")
    except Exception:
        pass
    spawner = HealthInstanceSpawner()
    registry = HealthRegistry()

    spawn_attempts.inc()
    try:
        record = await registry.get_by_setup_token(setup_token)
        tier = (record.tier if record else "standard") if record else "standard"
        spawn = spawner.spawn_instance(
            user_id=setup_token,
            config_json=config_json,
            onboarding_submission=submission,
            tier=tier,
            extra_env=_build_setup_spawn_env(
                payload=payload,
                health_secret=health_secret,
                telegram_token=telegram_token,
            ),
        )
        spawn_success.inc()
    except Exception:
        spawn_failures.inc()
        raise

    user_id = record.id if record else setup_token
    await registry.set_container(
        user_id=user_id,
        container_id=spawn.container_id,
        workspace_volume=spawn.volume_name,
        status="active",
    )
    health.mark_setup_active()
    return {"status": "ok", "containerId": spawn.container_id}


class WorkerSettings:
    functions = [spawn_instance_job]
    redis_settings = RedisSettings.from_dsn(
        os.environ.get("ARQ_REDIS_URL", "redis://redis:6379/0")
    )


async def _run() -> None:
    worker = Worker(
        functions=WorkerSettings.functions,
        redis_settings=WorkerSettings.redis_settings,
    )
    logger.info("health.worker.starting")
    await worker.async_run()


def main() -> None:
    _configure_logging()
    try:
        asyncio.run(_run())
    except Exception:
        logger.exception("health.worker.crashed")
        raise


if __name__ == "__main__":
    main()
