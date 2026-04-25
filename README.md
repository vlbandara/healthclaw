<div align="center">
  <img src="nanobot_logo.png" alt="Healthclaw" width="200">
  <h1>Healthclaw</h1>
  <p><strong>Private wellbeing companion that learns your rhythm.</strong></p>
  <p>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <img src="https://img.shields.io/badge/local--first-Ollama%20%2B%20Gemma-orange" alt="Local First">
    <a href="https://github.com/HKUDS/nanobot"><img src="https://img.shields.io/badge/forked%20from-nanobot-1f6feb" alt="Forked from nanobot"></a>
  </p>
</div>

<br>

<div align="center">
  <img src="docs/assets/Healthclaw_hero.png" alt="Healthclaw — A companion that checks in like it knows you" width="720">
</div>

<br>

> A companion that checks in like it knows you. Calm, personal, and always around.
> Medication, movement, stress, sleep, or just daily rhythm — start with a few quick choices and it will keep learning what actually helps.

---

## What is Healthclaw?

Healthclaw is a **private AI wellbeing companion** that runs on your own machine. It talks to you through Telegram (or other channels), remembers your habits and goals, checks in on your schedule, and learns what actually helps you over time.

It's not a clinical chatbot. It's the coach who texts you back at midnight, calls out your excuses without being mean, and actually remembers what you said three weeks ago.

**The key idea:** Run it locally with [Google's Gemma](https://ai.google.dev/gemma) via [Ollama](https://ollama.com/) — your conversations never leave your machine. Onboard your whole family, and each member gets their own **completely isolated** companion with zero data leakage between them.

---

## Why Healthclaw?

| | |
|---|---|
| 🔒 **Fully private** | Run 100% locally with Gemma via Ollama. No API subscriptions, no data sent anywhere |
| 👨‍👩‍👧‍👦 **Family mode** | Each family member gets their own isolated Docker workspace — separate memory, separate personality |
| 🧠 **Remembers you** | Layered memory system that consolidates and reflects, not just stores |
| 💬 **Feels human** | Warm, direct, sometimes dry — never corporate. See the [prompt architecture](docs/NATURAL_COMPANION_PROMPTS.md) |
| 🌙 **2am mode** | Knows when to be quiet and grounding at night, when to push during the day |
| ⏰ **Proactive** | Daily heartbeat check-ins, medication reminders, habit tracking — on your schedule |
| 🔌 **Multi-channel** | Telegram, Discord, Slack, WhatsApp, Matrix, and more |

---

## Quick Start — Local & Private (Recommended)

This is the recommended path. Your data stays on your machine. No API keys needed.

### Prerequisites

- [Docker & Docker Compose](https://docs.docker.com/get-docker/)
- [Ollama](https://ollama.com/) installed on your host

### 1. Pull a Gemma model

```bash
# Recommended: Gemma 7B (needs ~8GB RAM)
ollama pull gemma:7b

# Lighter alternative: Gemma 2B (needs ~4GB RAM)
ollama pull gemma:2b
```

### 2. Clone & configure

```bash
git clone https://github.com/vlbandara/Healthclaw.git
cd Healthclaw

# Create your local config from the template
cp .env.example .env
```

The defaults in `.env.example` already point to local Ollama. Just add your Telegram bot token:

```bash
# Get a bot token from @BotFather on Telegram, then:
# Edit .env and set TELEGRAM_BOT_TOKEN=your-token-here
```

### 3. Start the stack

```bash
docker compose --env-file .env up -d --build postgres redis orchestrator worker
```

### 4. Say hello

Search for your bot on Telegram and send a message. Healthclaw will greet you and begin the wellbeing onboarding conversation.

> 📖 **Full walkthrough:** [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)

---

## Quick Start — Cloud API

If you prefer a cloud LLM (Claude, GPT-4, etc.) instead of running locally:

```bash
git clone https://github.com/vlbandara/Healthclaw.git
cd Healthclaw
cp .env.example .env
```

Edit `.env` and switch to a cloud provider:

```bash
NANOBOT_AGENTS__DEFAULTS__PROVIDER=openrouter
NANOBOT_AGENTS__DEFAULTS__MODEL=anthropic/claude-opus-4-5
# Add your API key from https://openrouter.ai/
MINIMAX_API_KEY=sk-or-v1-your-key-here
```

Then start the stack the same way:

```bash
docker compose --env-file .env up -d --build postgres redis orchestrator worker
```

---

## Family Onboarding

This is the killer feature. Healthclaw isolates every user into their own Docker workspace with separate memory, config, and health profile. No data ever crosses between family members.

```
NANOBOT_MULTI_TENANT=true   # Already set in .env.example
```

1. **Mom** sends "Hi" → Healthclaw spins up an isolated workspace just for her
2. **Dad** sends "Hi" → Completely separate workspace, separate memory
3. **You** send "Hi" → Your own private companion

Each person gets a personalized wellbeing coach that remembers only their context. All processed against your private local Gemma instance.

> 📖 **Full guide:** [docs/FAMILY_WELLBEING_LOCAL_SETUP.md](docs/FAMILY_WELLBEING_LOCAL_SETUP.md)

---

## What it does

**Habit coaching** — Checks in daily, tracks patterns, defends your routines against drift. Relapse recovery, not guilt.

**Sleep support** — Monitors sleep quality, connects it to your goals. No lectures at midnight — just one anchor, one next move.

**Health onboarding** — Gathers your health profile through natural conversation. No form-filling.

**Medication reminders** — Cron-powered reminders delivered on your schedule, through your preferred channel.

**Daily heartbeat** — Periodic background check-ins on a configurable interval. Stays in touch even when you haven't opened the app.

**Memory that reflects** — Not just storage. Dream consolidation runs periodically to turn raw conversation into durable, curated knowledge about you.

---

## Architecture

```
 ┌─────────────────────────────────────────────────────┐
 │                   Telegram / Channels                │
 └──────────────────────┬──────────────────────────────┘
                        │
 ┌──────────────────────▼──────────────────────────────┐
 │                  Healthclaw Gateway                    │
 │  ┌────────────┐  ┌───────────┐  ┌───────────────┐  │
 │  │  channels  │  │  providers │  │    skills     │  │
 │  └────────────┘  └───────────┘  └───────────────┘  │
 │  ┌────────────┐  ┌───────────┐  ┌───────────────┐  │
 │  │   agent    │  │   cron    │  │   session     │  │
 │  └────────────┘  └───────────┘  └───────────────┘  │
 │  ┌──────────────────────────────────────────────┐  │
 │  │         SOUL · MEMORY · HEARTBEAT            │  │
 │  │      (wellbeing-specific prompt layers)       │  │
 │  └──────────────────────────────────────────────┘  │
 └─────────────────────────────────────────────────────┘
                        │
           ┌────────────┴────────────┐
           │   Per-User Workspace    │
           │  (isolated Docker env)  │
           │  - SOUL.md & USER.md    │
           │  - memory/history.jsonl │
           │  - health profile       │
           └─────────────────────────┘
```

Each user runs in an isolated Docker workspace: their own config, memory, conversation history, and health profile — fully private.

> 📖 **Deep dive:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Chat Channels

| Channel | Setup |
|---------|-------|
| **Telegram** | Bot token from [@BotFather](https://t.me/BotFather) |
| **Discord** | Bot token + Message Content intent |
| **Slack** | Socket Mode (no public URL needed) |
| **WhatsApp** | QR scan (`nanobot channels login whatsapp`) |
| **Matrix** | Homeserver URL + access token |
| **Email** | IMAP/SMTP credentials |

> 📖 **Channel plugin guide:** [docs/CHANNEL_PLUGIN_GUIDE.md](docs/CHANNEL_PLUGIN_GUIDE.md)

---

## AI Providers

| Provider | Notes |
|----------|-------|
| `ollama` | **Recommended** — Local, private, free. Gemma, Llama, Mistral, etc. |
| `openrouter` | Access to all cloud models via one API |
| `anthropic` | Claude direct |
| `openai` | GPT direct |
| `deepseek` | DeepSeek direct |
| `groq` | Free Whisper transcription for voice messages |
| `vllm` / `ovms` | Local OpenAI-compatible servers |
| `custom` | Any OpenAI-compatible endpoint |

---

## Memory System

Healthclaw uses a layered memory architecture:

- **Session** — Live conversation context
- **History** (`memory/history.jsonl`) — Append-only compressed conversation archive
- **Dream** — Periodic consolidation that distills history into structured knowledge
- **Long-term** (`SOUL.md`, `USER.md`, `MEMORY.md`) — Curated, durable knowledge files
- **Git-backed** — Memory changes are versioned and restorable

| Command | What it does |
|---------|--------------|
| `/dream` | Run Dream memory consolidation now |
| `/dream-log` | Show latest memory change |
| `/dream-restore <sha>` | Restore memory to a previous state |

> 📖 **Full documentation:** [docs/MEMORY.md](docs/MEMORY.md)

---

## In-Chat Commands

| Command | What it does |
|---------|--------------|
| `/new` | Start a new conversation |
| `/stop` | Stop the current task |
| `/restart` | Restart the bot |
| `/status` | Show bot status |
| `/dream` | Run Dream consolidation |
| `/dream-log` | Show latest Dream change |
| `/dream-restore <sha>` | Restore memory to before a specific change |

---

## Configuration & Customization

- **Personality:** Edit `SOUL.md` to change your companion's voice and style
- **Tone presets:** Gentle, Direct, or Calm — [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md)
- **Prompts:** See the full [prompt architecture](docs/NATURAL_COMPANION_PROMPTS.md)
- **Self-hosting:** Deploy on any VPS — [docs/SELF_HOSTING.md](docs/SELF_HOSTING.md)
- **Security hardening:** Production checklist — [SECURITY.md](SECURITY.md)

---

## Docker

```bash
# Build
docker build -t Healthclaw .

# First-time setup
docker run -v ~/.nanobot:/root/.nanobot --rm Healthclaw onboard

# Start the gateway
docker run -v ~/.nanobot:/root/.nanobot -p 18790:18790 Healthclaw gateway
```

Or with Docker Compose (recommended):

```bash
cp .env.example .env
# Edit .env with your settings
docker compose --env-file .env up -d --build
```

---

## Contributing

We welcome contributions of all sizes. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- 🐛 [Report a bug](https://github.com/vlbandara/Healthclaw/issues/new?template=bug_report.md)
- 💡 [Request a feature](https://github.com/vlbandara/Healthclaw/issues/new?template=feature_request.md)
- 💬 [Ask a question](https://github.com/vlbandara/Healthclaw/discussions)

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Getting Started](docs/GETTING_STARTED.md) | Step-by-step beginner guide |
| [Family Setup](docs/FAMILY_WELLBEING_LOCAL_SETUP.md) | Multi-user local deployment |
| [Architecture](docs/ARCHITECTURE.md) | System design deep dive |
| [Memory System](docs/MEMORY.md) | How memory works |
| [Customization](docs/CUSTOMIZATION.md) | Personality, tone, and skills |
| [Self-Hosting](docs/SELF_HOSTING.md) | Deploy on your own server |
| [Security](SECURITY.md) | Security best practices |
| [Prompt Architecture](docs/NATURAL_COMPANION_PROMPTS.md) | How the companion voice works |
| [Channel Plugins](docs/CHANNEL_PLUGIN_GUIDE.md) | Add new chat channels |
| [FAQ](docs/FAQ.md) | Common questions |

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for what's planned and how to help shape the direction.

---

## Acknowledgements

Healthclaw is a wellbeing-focused fork of [nanobot](https://github.com/HKUDS/nanobot) by the HKUDS team. We're grateful for their excellent foundation.

---

## License

[MIT](LICENSE) — use it, modify it, share it.

*Healthclaw is for educational, research, and personal use. It is not a medical device and not a substitute for professional healthcare.*