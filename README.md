<div align="center">

![Healthclaw — Private AI Wellbeing Companion](docs/assets/healthclaw_hero.png)

# Healthclaw

**Private, local-first wellbeing companions for individuals and families.**

[![Python ≥3.11](https://img.shields.io/badge/python-%E2%89%A53.11-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://github.com/vlbandara/healthclaw/actions/workflows/ci.yml/badge.svg)](https://github.com/vlbandara/healthclaw/actions/workflows/ci.yml)
[![Forked from nanobot](https://img.shields.io/badge/forked%20from-nanobot-1f6feb)](https://github.com/HKUDS/nanobot)

</div>

> **Fork notice**
>
> Healthclaw is a fork of [nanobot](https://github.com/HKUDS/nanobot), adapted for a privacy-first wellbeing companion experience.
> The public product name is **Healthclaw**.
> For v0.2 compatibility, some internal identifiers still use `nanobot`, including the Python package, CLI command, config paths, and `NANOBOT_*` environment variables.

## What It Is

Healthclaw runs a personal AI companion on infrastructure you control. It can talk through Telegram and other channels, keep isolated long-term memory per user, run scheduled check-ins, and support family-style multi-tenant setups where each person gets a separate workspace.

This repository is aimed at self-hosters and contributors who want:

- local-first deployment with Ollama + Gemma
- a clear path to cloud providers when local models are not practical
- isolated workspaces for multiple users
- documented behavior, reproducible builds, and public CI

Healthclaw is for educational, personal, and research use. It is **not** a medical device and not a substitute for professional healthcare.

## Highlights

- **Private by default**: local model support via Ollama keeps prompts and memory on your machine
- **Fork with compatibility**: Healthclaw branding on public surfaces, `nanobot` runtime identifiers preserved for v0.2
- **Multi-tenant family mode**: separate workspace, memory, and profile per user
- **Channel support**: Telegram plus other channels supported by the underlying nanobot architecture
- **Operator-friendly**: Docker, migrations, health endpoints, tests, and CI included

## Quick Start

### Local and Private

```bash
git clone https://github.com/vlbandara/healthclaw.git
cd healthclaw
cp .env.example .env
```

Install Ollama and pull a model:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma:7b
```

Set at least these values in `.env`:

```env
NANOBOT_AGENTS__DEFAULTS__PROVIDER=ollama
NANOBOT_AGENTS__DEFAULTS__MODEL=gemma:7b
OLLAMA_API_BASE=http://host.docker.internal:11434
TELEGRAM_BOT_TOKEN=123456789:your-token
HEALTH_VAULT_KEY=generate-a-fernet-key
POSTGRES_PASSWORD=change-me
```

Start the stack:

```bash
docker compose --env-file .env up -d --build postgres redis orchestrator worker
```

Open the onboarding surface at `http://localhost:18080`.

### Cloud Provider Path

You can also keep the Healthclaw product layer and use a hosted model provider:

```env
NANOBOT_AGENTS__DEFAULTS__PROVIDER=openrouter
NANOBOT_AGENTS__DEFAULTS__MODEL=anthropic/claude-opus-4-5
OPENROUTER_API_KEY=your-key
TELEGRAM_BOT_TOKEN=123456789:your-token
HEALTH_VAULT_KEY=generate-a-fernet-key
POSTGRES_PASSWORD=change-me
```

The Docker startup command stays the same.

## Runtime Compatibility

The following names remain unchanged in this release:

- CLI: `nanobot`
- Python package: `nanobot`
- env vars: `NANOBOT_*`
- default state directory: `~/.nanobot`

That compatibility layer is intentional for v0.2. Healthclaw is the public brand; `nanobot` is still the runtime identifier set.

## Documentation

- [Getting Started](docs/GETTING_STARTED.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Customization](docs/CUSTOMIZATION.md)
- [Family Local Setup](docs/FAMILY_WELLBEING_LOCAL_SETUP.md)
- [Self-Hosting](docs/SELF_HOSTING.md)
- [Local Development](docs/LOCAL_DEVELOPMENT.md)
- [FAQ](docs/FAQ.md)
- [Security Policy](SECURITY.md)

## Contributing

Healthclaw is an open-source fork of nanobot and contributions are welcome.

- [Contributing Guide](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [GitHub Discussions](https://github.com/vlbandara/healthclaw/discussions)
- [Issue Tracker](https://github.com/vlbandara/healthclaw/issues)

## Acknowledgements

Healthclaw builds on [nanobot](https://github.com/HKUDS/nanobot) by HKUDS. This fork keeps that foundation visible on purpose so contributors understand both the heritage and the compatibility choices in this repository.

## License

[MIT](LICENSE)
