# Getting Started with Healthclaw

Healthclaw v0.2 is a self-host beta. The recommended first run is local Ollama plus browser chat. Telegram and hosted model providers are optional after the local path works.

Healthclaw is the public product name for this fork. For compatibility, the Python package, legacy CLI command, workspace path, and many environment variables still use `nanobot`.

## Prerequisites

- Docker with the Compose plugin
- [Ollama](https://ollama.com/) on the host machine
- Python 3.11 through 3.13 for local development
- `uv` for dependency and command execution

## 1. Clone and Generate Local Config

```bash
git clone https://github.com/vlbandara/healthclaw.git
cd healthclaw
uv run healthclaw init-local --env-file .env.local
```

`init-local` writes a local-only env file with:

- local Ollama defaults
- a generated `HEALTH_VAULT_KEY`
- a generated `POSTGRES_PASSWORD`
- browser-chat-first setup
- `HEALTH_ENABLE_WHATSAPP=false`
- no provider keys copied from your shell

## 2. Install and Pull the Local Model

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma:7b
```

For lower-resource machines:

```bash
ollama pull gemma:2b
uv run healthclaw init-local --env-file .env.local --force --model gemma:2b
```

## 3. Validate the Local Setup

```bash
uv run healthclaw doctor --env-file .env.local
```

The doctor command validates required env values, Docker/Compose, Ollama reachability, the selected model, and `/healthz` if the stack is already running. It redacts secrets instead of printing raw compose output.

## 4. Start Healthclaw

```bash
docker compose --env-file .env.local up -d --build postgres redis orchestrator worker
uv run healthclaw doctor --env-file .env.local
```

Open:

- setup: `http://localhost:18080`
- health check: `http://localhost:18080/healthz`

Finish the setup flow, then use the browser chat link shown on completion.

## Optional: Telegram

Telegram is no longer required for the first local run. To add it:

1. Open Telegram and search for **BotFather**.
2. Send `/newbot`.
3. Copy the token.
4. Paste it in the Telegram step during setup.

If you connect Telegram after activation, restart the worker/orchestrator so the channel config is refreshed.

## Optional: Hosted Provider

If you do not want to run Ollama, choose the cloud-provider card in setup and paste an API key. OpenRouter is the simplest starting point:

```env
NANOBOT_AGENTS__DEFAULTS__PROVIDER=openrouter
NANOBOT_AGENTS__DEFAULTS__MODEL=openai/gpt-4o-mini
OPENROUTER_API_KEY=your-key
```

Do not paste real keys into issues, logs, screenshots, or chat.

## Useful Commands

```bash
uv run healthclaw init-local --env-file .env.local --force
uv run healthclaw doctor --env-file .env.local
uv run --extra dev ruff check nanobot tests
uv run --extra dev pytest -q
uv build
```

## Next Steps

- [Self-Hosting](SELF_HOSTING.md)
- [Local Development](LOCAL_DEVELOPMENT.md)
- [Architecture](ARCHITECTURE.md)
- [Customization](CUSTOMIZATION.md)
- [FAQ](FAQ.md)
