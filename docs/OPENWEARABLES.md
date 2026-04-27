# Open Wearables Integration

Healthclaw can optionally pull wearable summaries through a self-hosted or managed Open Wearables instance.

This first open-source release is:

- experimental
- setup-first
- focused on cloud/OAuth providers
- designed to keep durable wearable preferences separate from encrypted user mapping and cached snapshots

## Required Env Vars

Add these on the Healthclaw host that serves the health setup flow:

```env
OPENWEARABLES_ENABLED=true
OPENWEARABLES_API_URL=https://your-openwearables.example.com
OPENWEARABLES_API_KEY=ow_live_or_local_key
```

Optional tuning:

```env
OPENWEARABLES_TIMEOUT_SECONDS=20
OPENWEARABLES_SYNC_WINDOW_DAYS=3
OPENWEARABLES_STALE_AFTER_HOURS=36
```

These values are forwarded into spawned per-user Healthclaw instances so `/wearables` and `/wearables sync` work after activation.

## Local Dev Flow

1. Start Open Wearables separately and generate an API key in its dashboard.
2. Add the env vars above to `.env` or `.env.local`.
3. Start Healthclaw.
4. Open the hosted setup page.
5. On the new wearables step, choose a provider and complete the OAuth handoff.
6. Back on setup, run a sync or continue activation.

## What Healthclaw Stores

Durable profile:

- whether wearables are enabled
- preferred providers
- whether wearable context may influence coaching

Encrypted setup/runtime state:

- Open Wearables user mapping
- cached wearable snapshot used for prompt grounding

Plain runtime metadata:

- last sync time
- sync freshness
- connected provider names

Healthclaw does not dump raw high-volume wearable payloads into `USER.md`, `MEMORY.md`, or other durable prompt files.

## User-Facing Behavior

After activation:

- `/wearables` shows connection and sync state
- `/wearables sync` triggers a refresh
- health turns can reference a compact wearable snapshot when one exists

The snapshot is advisory context for wellness coaching only. It does not change the existing non-diagnostic safety posture.
