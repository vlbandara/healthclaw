# BiomeClaw Local Development

This repo now has an explicit split between production-tracking and local development:

- `main`: deployment-tracking branch for Hetzner.
- `local-dev` (or short-lived feature branches from it): day-to-day local work.
- `.worktrees/main-prod`: clean `main` checkout for quick production comparisons.

## Local Env Files

- `.env`: production-oriented values that get copied to the Hetzner server.
- `.env.local`: local-only values for your machine. Start from [.env.local.example](/Users/vinodhlahiru/Documents/Repos/nanobot/.env.local.example).

`.env.local` is gitignored, uses a separate Compose project name, and keeps runtime state under `.local/nanobot-state` instead of `~/.nanobot`.

## Local Docker Workflow

1. Create the local env file:

```bash
cp .env.local.example .env.local
```

2. Create local runtime directories:

```bash
mkdir -p .local/nanobot-state/workspace .local/nanobot-state/whatsapp-auth
```

3. Start the local health stack without touching the Hetzner server:

```bash
docker compose --env-file .env.local up -d --build postgres redis orchestrator worker whatsapp-bridge
```

4. Open the local API:

```bash
open http://localhost:18080
```

5. Stop it when done:

```bash
docker compose --env-file .env.local down
```

If you need local Caddy too, the example env maps it to `18081/18443` instead of `80/443`.

## Branch Workflow

Keep `main` clean and deployable. Do active work on `local-dev` or a feature branch cut from it. The production deploy workflow remains pinned to `main`, and the local `scripts/prod/deploy.sh` guard now rejects non-`main` branches unless you override it on purpose.
