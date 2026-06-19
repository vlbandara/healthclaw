# Local Development

Healthclaw is the public product name for this fork. For v0.2 compatibility, local development still uses the `nanobot` package, workspace path, and `NANOBOT_*` environment variables. Both `healthclaw` and `nanobot` CLI entrypoints are available.

## Local Environment

Create a local-only env file:

```bash
uv run healthclaw init-local --env-file .env.local
mkdir -p .local/nanobot-state/workspace
```

`.env.local` is gitignored and keeps runtime state inside the repository under `.local/nanobot-state`. The generated file does not copy API keys from your shell.

## Start the Local Stack

```bash
docker compose --env-file .env.local up -d --build postgres redis orchestrator worker
uv run healthclaw doctor --env-file .env.local
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
uv run --extra dev ruff check nanobot tests
uv run --extra dev pytest -q
uv build
uv run healthclaw doctor --env-file .env.local
cd bridge && npm ci && npm run build && npm audit --audit-level=critical
```

Use `healthclaw doctor` instead of pasting raw `docker compose config` output because compose output can include interpolated secrets.
