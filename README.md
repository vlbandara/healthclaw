<div align="center">

<a href="https://vlbandara.github.io/healthclaw/">
  <img src="docs/assets/healthclaw_repo_hero.png" alt="Healthclaw product page hero" width="920" />
</a>

# Healthclaw

**Private, local-first wellbeing companion with family-safe multi-tenancy, calm companion UX, and optional Open Wearables integration.**

Healthclaw turns the lightweight `nanobot` agent core into a calmer, more opinionated product for private wellbeing support, family-style multi-user setups, and self-hosted daily use.

[Product Page](https://vlbandara.github.io/healthclaw/) • [Getting Started](docs/GETTING_STARTED.md) • [Family Mode](docs/FAMILY_WELLBEING_LOCAL_SETUP.md) • [Open Wearables](docs/OPENWEARABLES.md)

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

The repo is intentionally positioned between a general-purpose agent framework and a narrow product wrapper: you still get a readable, hackable codebase, but the default experience is steered toward privacy-first wellbeing companionship rather than generic automation.

If you want the fast product overview first, use the public GitHub Pages site: [vlbandara.github.io/healthclaw](https://vlbandara.github.io/healthclaw/).

For a first-time visitor, the short version is:

- bring your own model provider: local Ollama or hosted APIs
- onboard through a web flow, then continue in chat
- keep each person isolated with separate memory and workspace state
- self-host the stack with Docker instead of relying on a SaaS backend

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

## Positioning

Healthclaw is best understood as a focused fork with two lineages:

- **From nanobot**: the lightweight Python agent core, chat-channel architecture, memory model, and self-hosting path
- **Alongside OpenClaw**: a more product-shaped agent experience, stronger opinionation around user workflows, and compatibility-minded skill conventions

That makes Healthclaw a better fit when you want a companion that feels deliberate and private, not just a general-purpose agent shell. The biggest differences are the health-specific onboarding and prompt stack, family-safe multi-tenancy with isolated per-user workspaces, and optional Open Wearables grounding for more context-aware coaching.

## Comparison

| Dimension | [OpenClaw](https://github.com/openclaw/openclaw) | [nanobot](https://github.com/HKUDS/nanobot) | Healthclaw |
|---|---|---|---|
| Primary goal | Cross-platform personal AI assistant | Ultra-lightweight personal AI agent | Privacy-first wellbeing companion |
| Core shape | Broader assistant platform with gateway-centric workflows and optional device apps | Small, readable Python core with channels, memory, MCP, and deployment docs | Opinionated fork of nanobot for health and daily support scenarios |
| Best fit | Users who want a general assistant across more surfaces and devices | Builders who want a minimal agent they can study and extend | Individuals or families who want a calmer self-hosted companion with isolated memory |
| Interaction style | Gateway plus optional desktop and mobile companion surfaces | CLI, chat channels, API, dev WebUI | Web onboarding plus Telegram-first companion flow |
| Privacy posture | Personal assistant platform with local control options | Self-hostable with local or hosted model providers | Explicitly local-first, with separate per-user workspaces and memory boundaries |
| Multi-tenancy model | General personal-assistant workflows across devices and apps | General-purpose agent runtime; health family isolation is not a built-in product story | Family-oriented multi-tenancy with isolated workspace, profile, memory, and runtime per user |
| Wearables support | Broad assistant platform; this repo does not position OpenClaw around Healthclaw-style wellness data grounding | No built-in Healthclaw wearables onboarding flow in the upstream product | Optional Open Wearables integration with provider linking, sync, encrypted snapshot storage, and coaching-aware summaries |
| Companion vibe | Personal assistant | Personal agent | Calm, grounded, coach-like companion shaped by health-specific onboarding, tone, lifecycle, and check-in prompts |
| Domain focus | General-purpose personal assistant | General-purpose personal agent | Wellbeing check-ins, companion conversations, and family-style tenancy |
| Runtime identity | `openclaw` brand and runtime | `nanobot` brand and runtime | `Healthclaw` brand with `nanobot` runtime compatibility in v0.2 |

## Product Page

The repo now includes a static GitHub Pages site in [`site/`](/Users/vinodhlahiru/Documents/Repos/nanobot/site/index.html) so visitors can understand Healthclaw without entering the live onboarding flow.

- Expected URL: [vlbandara.github.io/healthclaw](https://vlbandara.github.io/healthclaw/)
- Deploy source: `.github/workflows/pages.yml`
- Static assets: `site/assets/`
- Publish trigger: push to `main`

## Quick Start

No config files, no key generation, no accounts. You need Docker, and that's it.

```bash
git clone https://github.com/vlbandara/healthclaw.git
cd healthclaw
docker compose up
```

The first run generates its own secrets, applies database migrations, pulls the
published image, and starts the onboarding surface at **http://localhost:8080**.
Open it, create a workspace, and follow the setup flow.

> Prefer make? `make up` then `make smoke` to confirm it's healthy.

<details>
<summary><strong>Connect a model provider</strong></summary>

Each user picks their provider during web setup — no global config needed.

- **Local + private (Ollama):** install Ollama on the host and pull a model
  (`ollama pull gemma:7b`), then choose Ollama in the setup flow.
- **Hosted (OpenRouter / MiniMax):** paste your API key in the setup flow.

</details>

<details>
<summary><strong>Add Telegram</strong></summary>

Create a bot with [@BotFather](https://t.me/BotFather), copy the token, and paste
it into the Telegram step during setup. Each user can connect their own bot.
See [Telegram setup](docs/TELEGRAM_BOTFATHER_SETUP.md).

</details>

<details>
<summary><strong>Other ways to run it</strong></summary>

```bash
docker compose pull        # use the published GHCR image
docker compose build       # build the image locally instead
HEALTH_HTTP_PORT=9000 docker compose up   # change the web port
```

Advanced overrides (provider fallbacks, wearables, WhatsApp bridge, custom
secrets) live in [`.env.advanced.example`](.env.advanced.example). For a public
TLS deployment, see [Self-Hosting](docs/SELF_HOSTING.md). For the longer
walkthrough, see [Getting Started](docs/GETTING_STARTED.md).

</details>

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
- [Memory Model](docs/MEMORY.md)
- [Family Local Setup](docs/FAMILY_WELLBEING_LOCAL_SETUP.md)
- [Self-Hosting](docs/SELF_HOSTING.md)
- [Open Wearables Integration](docs/OPENWEARABLES.md)
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
