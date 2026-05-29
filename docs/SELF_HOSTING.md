# Self-Hosting

This guide covers a generic single-host, internet-facing deployment of **Healthclaw** with automatic TLS.

Healthclaw is a fork of `nanobot`. The public brand is Healthclaw, but the runtime identifiers remain `nanobot` in v0.2 for compatibility.

## Prerequisites

- Linux host with Docker and the Compose plugin
- 4 GB RAM recommended for small deployments
- A domain name with an A/AAAA record pointing at the host (for TLS)
- Ports 80 and 443 open (Caddy fetches Let's Encrypt certificates automatically)
- Ollama on the host if you want local models

## Clone

```bash
git clone https://github.com/vlbandara/healthclaw.git
cd healthclaw
```

Secrets (the vault key and Postgres password) are generated automatically on
first run — there is nothing to copy or hand-edit. For a public deployment you
only need to provide your domain.

## Start with TLS

The production overlay adds Caddy in front of the orchestrator and terminates
HTTPS for your domain:

```bash
DOMAIN=health.example.com \
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

(or `DOMAIN=health.example.com make prod-up`)

Caddy obtains and renews the certificate for `$DOMAIN` and reverse-proxies to the
orchestrator. `HEALTH_ONBOARDING_BASE_URL` defaults to `https://$DOMAIN`.

Validate:

```bash
docker compose ps
curl -fsS https://health.example.com/healthz
./scripts/smoke.sh   # set HEALTHCLAW_URL=https://health.example.com first
```

## Optional Overrides

Everything else is optional. Copy what you need from
[`.env.advanced.example`](../.env.advanced.example) into a `.env` file:

- `HEALTHCLAW_IMAGE` — pin a specific published tag instead of `:latest`
- `NANOBOT_STATE_DIR` — host path for persistent state instead of the named volume
- `MINIMAX_API_KEY` / `OPENROUTER_API_KEY` / `GROQ_API_KEY` — global provider fallbacks
- `HEALTH_VAULT_KEY` / `POSTGRES_PASSWORD` — inject your own secrets instead of the generated ones

## Local Model Notes

If Ollama runs on the host, make sure containers can reach it:

- `host.docker.internal:11434` works on Docker Desktop out of the box
- on Linux, ensure a host-gateway mapping is available

## Data and Compatibility

Persistent runtime data lives in the `nanobot_state` volume (or `NANOBOT_STATE_DIR`),
mounted at `/home/nanobot/.nanobot` inside the containers. Generated secrets live in
the `secrets` volume; the database in `pg_data`.

The CLI remains `nanobot`.

## Security Notes

- generated secrets stay inside Docker volumes — back them up if you need to migrate hosts
- if you inject your own `.env`, never commit it
- expose only ports 80/443 via Caddy; the orchestrator port is not published in the prod overlay
- the orchestrator mounts the Docker socket to spawn per-user coach containers — run it on a host you trust
