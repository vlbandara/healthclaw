# Local Development

Healthclaw is the public product name for this fork. For v0.2 compatibility, local development still uses the `nanobot` package, CLI, workspace path, and `NANOBOT_*` environment variables.

## Local Environment

Create a local-only env file:

```bash
cp .env.local.example .env.local
mkdir -p .local/nanobot-state/workspace .local/nanobot-state/whatsapp-auth
```

`.env.local` is gitignored and keeps runtime state inside the repository under `.local/nanobot-state`.

## Start the Local Stack

```bash
docker compose --env-file .env.local up -d --build postgres redis orchestrator worker
```

Open:

- onboarding surface: `http://localhost:18080`
- health check: `http://localhost:18080/healthz`

Stop it with:

```bash
docker compose --env-file .env.local down
```

## Useful Validation Commands

```bash
uv run ruff check nanobot tests
uv run pytest -q
uv build
docker compose config
cd bridge && npm ci && npm run build
```
