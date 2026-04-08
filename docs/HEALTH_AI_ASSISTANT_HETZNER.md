# BiomeClaw Hetzner Deployment

This deployment runs the hosted health experience for **BiomeClaw** on a single Hetzner VPS. The public brand is BiomeClaw, but the first release deliberately keeps the internal `nanobot` package, CLI, workspace path, and `NANOBOT_*` environment variables for runtime compatibility.

Only Caddy is exposed on `80/443`. The orchestrator, worker, Redis, and Postgres services stay on the Docker network.

## Target Host

- Existing Hetzner VPS: `46.62.231.14`
- Recommended profile: 2 vCPU / 4 GB RAM / 40 GB SSD or better
- Deployment path: `/opt/biomeclaw`
- Legacy app path to preserve before cutover: `/opt/TradingAgents`

## Required Files

On the local machine:

- This repo checked out from the future `BiomeClaw` GitHub fork
- A populated local `.env` file based on `.env.example`

On the server:

- Docker Engine with the Compose plugin installed
- Persistent runtime state under `~/.nanobot`

## Required Environment

Create `/opt/biomeclaw/.env` from [.env.example](/Users/vinodhlahiru/Documents/Repos/nanobot/.env.example) and provide at least:

```env
DOMAIN=health.example.com
MINIMAX_API_KEY=...
TELEGRAM_BOT_TOKEN=...
HEALTH_VAULT_KEY=...
POSTGRES_PASSWORD=...
HEALTH_ONBOARDING_BASE_URL=https://health.example.com
HEALTH_TELEGRAM_BOT_URL=https://t.me/your_bot_username
HEALTH_WHATSAPP_CHAT_URL=
WHATSAPP_BRIDGE_TOKEN=
```

`HEALTH_ONBOARDING_BASE_URL` should match the public HTTPS URL served by Caddy.

## Runtime State

Seed `~/.nanobot/config.json` from `examples/health/minimax.config.example.json`. Keep secrets in `.env`, not in `config.json`.

Important compatibility notes:

- Workspace remains `~/.nanobot/workspace`
- CLI remains `nanobot`
- Internal environment variables remain `NANOBOT_*`

Ensure the runtime directories exist before the first bring-up:

```bash
mkdir -p ~/.nanobot/workspace ~/.nanobot/whatsapp-auth
```

## Backup-First Cutover

Run these from the local repo root.

1. Sync the codebase to the new app directory:

```bash
rsync -avz \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='results' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  /Users/vinodhlahiru/Documents/Repos/nanobot/ \
  root@46.62.231.14:/opt/biomeclaw/
```

2. Copy the deployment environment file:

```bash
scp .env root@46.62.231.14:/opt/biomeclaw/.env
```

3. Stop the currently running stack, back up the old app directory, and prepare persistent state:

```bash
ssh root@46.62.231.14 '
set -eu
timestamp=$(date +%Y%m%d-%H%M%S)
if [ -d /opt/TradingAgents ]; then
  cd /opt/TradingAgents && docker compose down || true
  mv /opt/TradingAgents "/opt/TradingAgents.backup-$timestamp"
fi
mkdir -p /root/.nanobot/workspace /root/.nanobot/whatsapp-auth
'
```

4. Bring up BiomeClaw:

```bash
ssh root@46.62.231.14 '
set -eu
cd /opt/biomeclaw
docker compose up -d --build
'
```

## Verification

Run these after startup:

```bash
ssh root@46.62.231.14 'cd /opt/biomeclaw && docker compose ps'
ssh root@46.62.231.14 'cd /opt/biomeclaw && docker compose logs --tail=200'
curl -I https://health.example.com/healthz
```

Confirm:

- Caddy is serving the configured domain on `443`
- `/healthz` returns success
- The landing page, setup flow, and browser chat load
- Telegram onboarding works with the configured bot token

## Rollback

If the new stack fails validation:

```bash
ssh root@46.62.231.14 '
set -eu
cd /opt/biomeclaw && docker compose down || true
latest_backup=$(ls -dt /opt/TradingAgents.backup-* 2>/dev/null | head -n 1)
if [ -n "$latest_backup" ]; then
  mv "$latest_backup" /opt/TradingAgents
  cd /opt/TradingAgents && docker compose up -d --build
fi
'
```

Do not delete the backup until the new deployment has passed smoke checks.
