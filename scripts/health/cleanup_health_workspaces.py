#!/usr/bin/env python3
"""Audit and clean health workspaces after the proactive-delivery fixes land.

This script is intended for one-off production cleanup. It:

- removes queued autonomy proactive payloads
- archives off-domain autonomy artifacts and threads
- backfills ``health/runtime.json`` from the latest real user message
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from nanobot.health.storage import HealthWorkspace, is_health_workspace

OFF_DOMAIN_RE = re.compile(
    r"\b(?:guitar|guitars|korean|music|song|songs|album|albums|artist|artists|band|bands|coding|code|python|repo|github|docker)\b",
    re.IGNORECASE,
)
SYSTEM_SESSION_PREFIXES = ("heartbeat", "autonomy", "cron:")


def _workspace_candidates(root: Path) -> list[Path]:
    if is_health_workspace(root):
        return [root]
    if not root.exists():
        return []
    out: list[Path] = []
    for path in sorted(root.iterdir()):
        if path.is_dir() and is_health_workspace(path):
            out.append(path)
    return out


def _latest_real_user_message(workspace: Path) -> str:
    sessions_dir = workspace / "sessions"
    latest: str = ""
    if not sessions_dir.is_dir():
        return latest
    for path in sessions_dir.glob("*.jsonl"):
        try:
            rows = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        if not rows:
            continue
        try:
            meta = json.loads(rows[0])
        except Exception:
            meta = {}
        key = str(meta.get("key") or path.stem).strip()
        if key.startswith(SYSTEM_SESSION_PREFIXES):
            continue
        for raw in rows[1:]:
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            if payload.get("role") != "user":
                continue
            timestamp = str(payload.get("timestamp") or "").strip()
            if timestamp and timestamp > latest:
                latest = timestamp
    return latest


def _archive_off_domain_autonomy(workspace: Path, *, dry_run: bool) -> dict[str, int]:
    autonomy_dir = workspace / "autonomy"
    threads_path = autonomy_dir / "threads.json"
    artifacts_dir = autonomy_dir / "artifacts"
    archive_dir = autonomy_dir / "archive"

    archived_threads = 0
    archived_artifacts = 0

    threads_payload: dict[str, Any] = {"threads": []}
    if threads_path.exists():
        try:
            threads_payload = json.loads(threads_path.read_text(encoding="utf-8"))
        except Exception:
            threads_payload = {"threads": []}

    threads = threads_payload.get("threads") if isinstance(threads_payload, dict) else []
    kept_threads: list[dict[str, Any]] = []
    archived_paths: set[str] = set()
    for thread in threads or []:
        blob = " ".join(str(thread.get(key) or "") for key in ("topic", "cluster", "query", "nextSuggestedAction"))
        if OFF_DOMAIN_RE.search(blob):
            archived_threads += 1
            for artifact in thread.get("artifactPaths") or []:
                archived_paths.add(str(artifact))
            continue
        kept_threads.append(thread)

    if artifacts_dir.is_dir():
        for artifact_path in artifacts_dir.glob("*.md"):
            rel = ""
            try:
                rel = str(artifact_path.relative_to(workspace))
            except Exception:
                rel = str(artifact_path)
            if OFF_DOMAIN_RE.search(artifact_path.name) or rel in archived_paths:
                archived_artifacts += 1
                if not dry_run:
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(artifact_path), str(archive_dir / artifact_path.name))

    if not dry_run and threads_path.exists():
        threads_path.write_text(
            json.dumps({"threads": kept_threads}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return {"threads": archived_threads, "artifacts": archived_artifacts}


def _backfill_runtime(workspace: Path, *, dry_run: bool) -> bool:
    health = HealthWorkspace(workspace)
    profile = health.load_profile() or {}
    timezone = str(profile.get("timezone") or "UTC").strip() or "UTC"
    latest_timestamp = _latest_real_user_message(workspace)
    if not latest_timestamp:
        return False
    try:
        latest = datetime.fromisoformat(latest_timestamp)
    except Exception:
        return False

    runtime = health.load_runtime()
    runtime["last_user_message_at"] = latest.astimezone(ZoneInfo("UTC")).isoformat()
    try:
        local_dt = latest.astimezone(ZoneInfo(timezone))
        runtime["last_user_local_date"] = local_dt.strftime("%Y-%m-%d")
    except Exception:
        runtime["last_user_local_date"] = runtime.get("last_user_local_date") or ""
    if not dry_run:
        health.save_runtime(runtime)
    return True


def _clear_pending(workspace: Path, *, dry_run: bool) -> bool:
    path = workspace / "autonomy" / "pending_proactive.json"
    if not path.exists():
        return False
    if not dry_run:
        path.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Workspace path(s) or directory roots containing workspaces.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect only; do not modify files.")
    args = parser.parse_args()

    workspaces: list[Path] = []
    for raw in args.paths:
        workspaces.extend(_workspace_candidates(Path(raw).expanduser().resolve()))

    if not workspaces:
        print("No health workspaces found.")
        return 0

    for workspace in workspaces:
        pending_cleared = _clear_pending(workspace, dry_run=args.dry_run)
        archived = _archive_off_domain_autonomy(workspace, dry_run=args.dry_run)
        runtime_backfilled = _backfill_runtime(workspace, dry_run=args.dry_run)
        print(
            json.dumps(
                {
                    "workspace": str(workspace),
                    "pendingCleared": pending_cleared,
                    "archivedThreads": archived["threads"],
                    "archivedArtifacts": archived["artifacts"],
                    "runtimeBackfilled": runtime_backfilled,
                    "dryRun": bool(args.dry_run),
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
