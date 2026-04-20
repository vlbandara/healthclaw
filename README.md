<div align="center">
  <img src="nanobot_logo.png" alt="BiomeClaw" width="420">
  <p>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    <a href="https://github.com/HKUDS/nanobot"><img src="https://img.shields.io/badge/forked%20from-nanobot-1f6feb" alt="Forked from nanobot"></a>
  </p>
  <h3>Your personal health companion — warm, sharp, and there at 2am.</h3>
</div>

---

BiomeClaw is a health-focused fork of [nanobot](https://github.com/HKUDS/nanobot). It gives you a private, isolated AI health coach that runs on your own infrastructure, talks to you through Telegram (or a dozen other channels), and remembers everything that matters.

You talk to it like a person. It keeps you honest.

---

## What it feels like

BiomeClaw is not a clinical chatbot. It's the coach who texts you back at midnight, calls out your excuses without being mean, and actually remembers what you said you wanted to do three weeks ago.

- Warm, direct, sometimes dry — never corporate
- Keeps track of your sleep, habits, goals, and what's actually happening in your life
- Remembers who you are — not just your data, but your name, your context, your patterns
- Doesn't lecture. Notices patterns, interrupts loops, builds momentum
- Knows when to be quiet and grounding at 2am, and when to push
- Non-judgmental on personal and intimate topics

---

## What it does

**Habit coaching**
Checks in daily, tracks patterns, defends your routines against drift and self-sabotage. Relapse recovery, not guilt.

**Sleep support**
Monitors your sleep quality, connects it to your goals, asks the right questions at the right time. No lectures at midnight — just one anchor, one next move.

**Health onboarding**
Gathers your health profile through natural conversation. No form-filling. Just a chat that gets smarter as you talk.

**Reminder system**
Cron-powered reminders for medications, check-ins, and routines — delivered on your schedule, through your preferred channel.

**Daily heartbeat**
Runs periodic background tasks on a configurable interval. Keeps you in the loop even when you haven't opened the app.

**Private & isolated**
Every user gets their own Docker workspace — their own config, memory, and model context. No data leaks, no cross-user contamination.

---

## Architecture

```
 ┌─────────────────────────────────────────────────────┐
 │                   Telegram / Channels                │
 └──────────────────────┬──────────────────────────────┘
                        │
 ┌──────────────────────▼──────────────────────────────┐
 │                    nanobot gateway                    │
 │  ┌────────────┐  ┌───────────┐  ┌───────────────┐  │
 │  │  channels  │  │  providers │  │    skills     │  │
 │  └────────────┘  └───────────┘  └───────────────┘  │
 │  ┌────────────┐  ┌───────────┐  ┌───────────────┐  │
 │  │   agent    │  │   cron    │  │   session     │  │
 │  └────────────┘  └───────────┘  └───────────────┘  │
 │  ┌──────────────────────────────────────────────┐  │
 │  │              SOUL · AGENTS · USER             │  │
 │  │         (health-specific prompt templates)    │  │
 │  └──────────────────────────────────────────────┘  │
 └─────────────────────────────────────────────────────┘
```

Every BiomeClaw instance runs as an isolated Docker container with its own workspace: config, memory, session history, and health profile — fully private to that user.

---

## Quick start

```bash
# Install
pip install nanobot-ai

# Onboard (creates ~/.nanobot/ with health workspace templates)
nanobot onboard

# Start talking
nanobot agent
```

Or connect Telegram right away:

```bash
nanobot gateway
```

Edit `~/.nanobot/config.json` to set your provider API key and Telegram bot token. That's it.

---

## Setup

### 1. Configure your AI provider

```json
// ~/.nanobot/config.json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-..."
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "provider": "openrouter"
    }
  }
}
```

### 2. Connect Telegram

Create a bot via [@BotFather](https://t.me/BotFather), then:

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"]
    }
  }
}
```

Find your `USER_ID` in Telegram settings (shown without the `@`). Use `["*"]` to allow everyone.

### 3. Run the gateway

```bash
nanobot gateway
```

Your bot is now live. It will greet new users with the health onboarding conversation and set up their private workspace on first contact.

---

## Chat channels

| Channel | Setup |
|---------|-------|
| **Telegram** | Bot token from @BotFather |
| **Discord** | Bot token + Message Content intent |
| **WhatsApp** | QR scan (`nanobot channels login whatsapp`) |
| **WeChat** | QR scan via ilinkai API |
| **Feishu** | App ID + App Secret (WebSocket, no public IP needed) |
| **Slack** | Socket Mode (no public URL needed) |
| **DingTalk** | AppKey + AppSecret (Stream mode) |
| **Matrix** | Homeserver URL + access token |
| **Email** | IMAP/SMTP credentials |
| **QQ** | App ID + App Secret |

For channel plugin development, see [docs/CHANNEL_PLUGIN_GUIDE.md](./docs/CHANNEL_PLUGIN_GUIDE.md).

---

## AI providers

| Provider | Notes |
|----------|-------|
| `openrouter` | Recommended — access to all models |
| `anthropic` | Claude direct |
| `openai` | GPT direct |
| `deepseek` | DeepSeek direct |
| `groq` | Free Whisper transcription for voice messages |
| `ollama` | Local models via Ollama |
| `vllm` / `ovms` | Local OpenAI-compatible servers |
| `custom` | Any OpenAI-compatible endpoint |

Adding a new provider takes 2 steps — add a `ProviderSpec` entry and a config field. See [docs/PYTHON_SDK.md](./docs/PYTHON_SDK.md).

---

## Memory & persistence

BiomeClaw uses a layered memory system:

- `memory/history.jsonl` — append-only summarized conversation history
- `SOUL.md`, `USER.md`, `memory/MEMORY.md` — long-term knowledge managed by Dream (periodic consolidation)
- `HEARTBEAT.md` — periodic tasks that run on a schedule

Dream runs on a configurable interval and can also be triggered manually via `/dream`.

---

## In-chat commands

| Command | What it does |
|---------|--------------|
| `/new` | Start a new conversation |
| `/stop` | Stop the current task |
| `/restart` | Restart the bot |
| `/status` | Show bot status |
| `/dream` | Run Dream memory consolidation now |
| `/dream-log` | Show latest Dream memory change |
| `/dream-restore <sha>` | Restore memory to before a specific change |

---

## Security

| Setting | Default | What it does |
|---------|---------|--------------|
| `tools.restrictToWorkspace` | `false` | Restricts all file/shell tools to the workspace directory |
| `tools.exec.sandbox` | `""` | Set to `"bwrap"` to sandbox shell commands (Linux only) |
| `tools.exec.enable` | `true` | Set to `false` to fully disable shell execution |
| `channels.*.allowFrom` | `[]` (deny all) | Whitelist of user IDs; `["*"]` to allow everyone |

For production deployments: set `"restrictToWorkspace": true` and `"tools.exec.sandbox": "bwrap"`.

---

## Docker

```bash
# Build
docker build -t biomeclaw .

# First-time setup
docker run -v ~/.nanobot:/root/.nanobot --rm biomeclaw onboard

# Start the gateway
docker run -v ~/.nanobot:/root/.nanobot -p 18790:18790 biomeclaw gateway
```

Or with Docker Compose:

```bash
docker compose run --rm biomeclaw-cli onboard
vim ~/.nanobot/config.json
docker compose up -d biomeclaw-gateway
```

---

## Supported channels & providers

Python 3.11+ · Typer CLI · FastAPI · Anthropic SDK · OpenAI SDK · MCP · Docker

---

*BiomeClaw is a fork of [nanobot](https://github.com/HKUDS/nanobot) for educational, research, and personal use. Not a medical device. Not a substitute for professional care.*