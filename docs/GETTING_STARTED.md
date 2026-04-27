# Getting Started with Healthclaw

This guide walks you through setting up Healthclaw for the first time. We'll cover both the **local (private)** path using Ollama + Gemma, and the **cloud API** path.

Healthclaw is the public product name for this fork. In v0.2, some runtime identifiers still use `nanobot`, including the CLI command, workspace path, and `NANOBOT_*` environment variables.

## Choose Your Path

| | Local + Private (Recommended) | Cloud API |
|---|---|---|
| Privacy | 100% local, no data leaves your machine | Data sent to third-party API |
| Setup | Requires Ollama installed | Requires API key only |
| Cost | Free (local Gemma) | Pay for API usage |
| Hardware | 8GB+ RAM recommended | Any machine |

---

## Option A: Local Setup (Recommended)

This path keeps all your conversations 100% on your machine using Google's Gemma model via Ollama.

### Prerequisites

- [Docker Desktop](https://docs.docker.com/get-docker/) (Mac, Windows, or Linux)
- [Ollama](https://ollama.com/) installed on your host machine
- 8GB+ RAM for Gemma 7B (or 4GB+ for Gemma 2B)

### Step 1: Install Ollama and Pull Gemma

```bash
# Install Ollama (macOS/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Or on macOS, install via Homebrew
brew install ollama

# Pull the Gemma 7B model (recommended)
ollama pull gemma:7b

# Or for lower-resource machines, use Gemma 2B
# ollama pull gemma:2b
```

### Step 2: Clone and Configure

```bash
git clone https://github.com/vlbandara/healthclaw.git
cd healthclaw

# Create your config from the template
cp .env.example .env

# Open .env in your editor and set your Telegram bot token
# See Step 3 below
```

### Step 3: Get a Telegram Bot Token

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts, give it a name and username
4. Copy the token BotFather gives you
5. Add it to your `.env` file:
   ```
   TELEGRAM_BOT_TOKEN=123456789:YOUR_TOKEN_HERE
   ```

### Step 4: Verify Ollama is Running

```bash
# Test that Ollama is accessible
curl http://localhost:11434

# You should see: {"status":"ok"}
```

### Step 5: Start the Stack

```bash
docker compose --env-file .env up -d --build postgres redis orchestrator worker

# Watch the logs to confirm everything started
docker compose --env-file .env logs -f
```

### Step 6: Say Hello

Open Telegram, find your bot by its username, and send a message like "Hi".

Healthclaw will greet you and begin a brief wellbeing onboarding conversation to personalize your experience.

---

## Option B: Cloud API Setup

If you prefer not to run locally, you can use a cloud LLM via OpenRouter or other providers.

### Step 1: Clone and Configure

```bash
git clone https://github.com/vlbandara/healthclaw.git
cd healthclaw

cp .env.example .env
```

### Step 2: Get an API Key

**OpenRouter** (recommended — unified access to many models):

1. Go to [openrouter.ai](https://openrouter.ai/)
2. Sign up and get an API key
3. Add to `.env`:
   ```
   NANOBOT_AGENTS__DEFAULTS__PROVIDER=openrouter
   NANOBOT_AGENTS__DEFAULTS__MODEL=openai/gpt-4o-mini
   OPENROUTER_API_KEY=sk-or-v1-your-key-here
   ```

Or use other providers directly:

```env
# Anthropic direct
NANOBOT_AGENTS__DEFAULTS__PROVIDER=anthropic
NANOBOT_AGENTS__DEFAULTS__MODEL=claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI direct
NANOBOT_AGENTS__DEFAULTS__PROVIDER=openai
NANOBOT_AGENTS__DEFAULTS__MODEL=gpt-4o
OPENAI_API_KEY=sk-...
```

### Step 3: Add Telegram Token

As in Option A, get a Telegram bot token from @BotFather and add it to `.env`.

### Step 4: Start the Stack

```bash
docker compose --env-file .env up -d --build postgres redis orchestrator worker
```

Open the onboarding surface at `http://localhost:18080`.

---

## Initial Configuration

After your first login, you can customize your experience:

### Memory Commands

| Command | What it does |
|---------|--------------|
| `/dream` | Run memory consolidation now |
| `/dream-log` | See the last memory change |
| `/dream-restore <sha>` | Restore memory to before a specific change |

### Voice and Tone

Healthclaw supports three tone presets. Set in `SOUL.md` or via the personality config:

- **Gentle** — Warm, soft landings, less pressure
- **Direct** — Clear, concise, names avoidance directly
- **Calm** — Quiet, steady, low stimulation (good for late night)

---

## Hardware Guidance

| Model | RAM Required | Use Case |
|-------|-------------|----------|
| Gemma 2B | 4GB | Testing, low-resource machines |
| Gemma 7B | 8GB | Recommended for most users |
| Gemma 27B | 16GB+ | Higher quality, requires more resources |

Run `ollama run gemma:7b` to verify it works. Exit with `/bye`.

---

## Next Steps

- [Family Setup](FAMILY_WELLBEING_LOCAL_SETUP.md) — Onboard multiple family members
- [Architecture](ARCHITECTURE.md) — Understand how Healthclaw works
- [Customization](CUSTOMIZATION.md) — Adjust personality and tone
- [FAQ](FAQ.md) — Common questions and troubleshooting

---

## Troubleshooting

**Ollama not responding:**
```bash
# Restart Ollama
ollama serve

# Check if it's running
ps aux | grep ollama
```

**Docker permission issues (Linux):**
```bash
# Add yourself to the docker group
sudo usermod -aG docker $USER
# Then log out and back in
```

**Can't find your bot on Telegram:**
- Verify `TELEGRAM_BOT_TOKEN` is correct in `.env`
- Restart the stack: `docker compose --env-file .env restart worker`
- Check logs: `docker compose --env-file .env logs worker | tail -50`
