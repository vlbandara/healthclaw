# Self-Hosting

This guide covers a generic single-host deployment of **Healthclaw** on your own server.

Healthclaw is a fork of `nanobot`. The public brand is Healthclaw, but the runtime identifiers remain `nanobot` in v0.2 for compatibility.

## Prerequisites

- Linux host with Docker and the Compose plugin
- 4 GB RAM recommended for small deployments
- Ollama on the host if you want local models
- a Telegram bot token if you want Telegram onboarding or chat

## Clone and Configure

```bash
git clone https://github.com/vlbandara/healthclaw.git
cd healthclaw
cp .env.example .env
```

Set at least:

```env
NANOBOT_AGENTS__DEFAULTS__PROVIDER=ollama
NANOBOT_AGENTS__DEFAULTS__MODEL=gemma:7b
OLLAMA_API_BASE=http://host.docker.internal:11434
TELEGRAM_BOT_TOKEN=123456789:your-token
HEALTH_VAULT_KEY=generate-a-fernet-key
POSTGRES_PASSWORD=change-me
DOMAIN=your-domain.example
HEALTH_ONBOARDING_BASE_URL=https://your-domain.example
```

## Start the Stack

```bash
docker compose --env-file .env up -d --build postgres redis orchestrator worker caddy
```

Validate:

```bash
docker compose ps
curl -fsS http://localhost:18080/healthz
```

## Local Model Notes

If Ollama runs on the host, make sure the containers can reach it.

Common options:

- `OLLAMA_API_BASE=http://host.docker.internal:11434`
- on Linux, add host gateway mapping if needed

## Data and Compatibility

Persistent runtime data remains under:

- `~/.nanobot`
- `~/.nanobot/workspace`
- `~/.nanobot/whatsapp-auth`

The CLI remains:

```bash
nanobot
```

## Security Notes

- never commit real `.env` files
- use a strong `POSTGRES_PASSWORD`
- protect `~/.nanobot`
- expose only the reverse-proxy ports you actually need
- prefer HTTPS for any internet-facing deployment
