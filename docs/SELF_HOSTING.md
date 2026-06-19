# Self-Hosting

This guide covers the supported public launch posture: a single-host Healthclaw self-host beta. Hosted multi-tenant operation is deferred.

## Prerequisites

- Linux host or local machine with Docker and the Compose plugin
- 4 GB RAM minimum; 8 GB+ recommended for Gemma 7B
- Ollama on the host for the private local-model path
- Optional Telegram bot token if you want chat-app delivery

## Clone and Configure

```bash
git clone https://github.com/vlbandara/healthclaw.git
cd healthclaw
uv run healthclaw init-local --env-file .env.local
```

For a server, edit `.env.local` after generation:

```env
DOMAIN=your-domain.example
HEALTH_ONBOARDING_BASE_URL=https://your-domain.example
CADDY_HTTP_PORT=80
CADDY_HTTPS_PORT=443
```

Do not paste raw `docker compose config` output into issues or chats; it can include interpolated secrets. Use:

```bash
uv run healthclaw doctor --env-file .env.local
```

## Start the Stack

Local browser-first setup:

```bash
docker compose --env-file .env.local up -d --build postgres redis orchestrator worker
```

Server with Caddy:

```bash
docker compose --env-file .env.local up -d --build postgres redis orchestrator worker caddy
```

Validate:

```bash
uv run healthclaw doctor --env-file .env.local
curl -fsS http://localhost:18080/healthz
```

## Data and Compatibility

Persistent runtime data remains under:

- `~/.nanobot` by default
- the generated `NANOBOT_STATE_DIR` for local development
- `memory/`, `health/`, and workspace files inside that state directory

CLI entrypoints:

```bash
healthclaw
nanobot
```

## Optional Channels

Browser chat is the default first-run channel. Telegram can be connected during setup. WhatsApp is hidden for the public launch and remains experimental behind:

```env
HEALTH_ENABLE_WHATSAPP=true
```

See [WhatsApp Experimental](WHATSAPP_EXPERIMENTAL.md) before enabling it.

## Security Notes

- Never commit real `.env` files, tokens, provider credentials, or compose output with secrets.
- Rotate any key that appears in terminal logs, screenshots, chat, or issues.
- Use a strong `POSTGRES_PASSWORD` and protect the state directory.
- Expose only the reverse-proxy ports you actually need.
- Prefer HTTPS for any internet-facing deployment.
- Healthclaw is wellbeing support, not a medical device or emergency-response system.
