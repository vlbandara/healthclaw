# Getting Started with Healthclaw

This guide walks you through setting up Healthclaw for the first time.

Healthclaw is the public product name for this fork. In v0.2, some runtime identifiers still use `nanobot`, including the CLI command, workspace path, and `NANOBOT_*` environment variables.

The only prerequisite is **Docker** ([Docker Desktop](https://docs.docker.com/get-docker/) on Mac/Windows, Docker Engine on Linux). Everything else — secrets, the database schema, the image — is handled for you.

---

## Step 1: Start the Stack

```bash
git clone https://github.com/vlbandara/healthclaw.git
cd healthclaw
docker compose up
```

On the first run Healthclaw will:

- generate a vault encryption key and a Postgres password (stored in a Docker volume — you never see or copy them),
- run database migrations,
- pull the published image (or build it locally if the image isn't available),
- start the onboarding surface on **http://localhost:8080**.

To run it in the background, use `docker compose up -d` (or `make up`). Confirm it's healthy with `make smoke`.

---

## Step 2: Create Your Workspace

Open **http://localhost:8080** and start the setup flow. Healthclaw provisions a private per-user workspace with isolated memory and profile state. You'll choose a model provider and (optionally) connect a chat channel.

---

## Step 3: Choose a Model Provider

Each user picks their provider during setup — there is no global model config to edit.

### Local + private (Ollama)

Keeps all conversations on your machine.

```bash
# Install Ollama on the host (macOS/Linux)
curl -fsSL https://ollama.com/install.sh | sh
# or: brew install ollama

# Pull a model
ollama pull gemma:7b      # 8GB+ RAM
# ollama pull gemma:2b    # lower-resource machines

# Verify it's reachable
curl http://localhost:11434
```

Then select **Ollama** in the setup flow. Containers reach the host via `host.docker.internal:11434`.

### Hosted provider (OpenRouter / MiniMax / others)

Paste your API key into the provider step during setup. No host installation required — good for lighter machines.

---

## Step 4: Connect Telegram (optional)

To talk to your companion over Telegram:

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the token BotFather gives you
4. Paste it into the **Telegram** step during setup

Each user connects their own bot. See [Telegram setup](TELEGRAM_BOTFATHER_SETUP.md) for screenshots. Wearables can be linked during setup too — see [Open Wearables](OPENWEARABLES.md).

---

## Step 5: Say Hello

Finish setup to provision your companion. Open Telegram (or your connected channel) and send "Hi" — Healthclaw greets you and begins a brief wellbeing onboarding to personalize your experience.

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

## Hardware Guidance (local models)

| Model | RAM Required | Use Case |
|-------|-------------|----------|
| Gemma 2B | 4GB | Testing, low-resource machines |
| Gemma 7B | 8GB | Recommended for most users |
| Gemma 27B | 16GB+ | Higher quality, requires more resources |

Run `ollama run gemma:7b` to verify it works. Exit with `/bye`.

---

## Next Steps

- [Family Setup](FAMILY_WELLBEING_LOCAL_SETUP.md) — Onboard multiple family members
- [Self-Hosting](SELF_HOSTING.md) — Deploy publicly with TLS
- [Architecture](ARCHITECTURE.md) — Understand how Healthclaw works
- [Customization](CUSTOMIZATION.md) — Adjust personality and tone
- [FAQ](FAQ.md) — Common questions and troubleshooting

---

## Troubleshooting

**See what's happening:**
```bash
docker compose logs -f          # all services
docker compose logs orchestrator
docker compose ps               # service status
```

**Ollama not reachable from containers:**
```bash
ollama serve                    # make sure it's running
curl http://localhost:11434     # should respond on the host
```
Containers connect via `host.docker.internal:11434` (works out of the box on Docker Desktop; on Linux ensure host networking or the `host.docker.internal` host mapping is available).

**Docker permission issues (Linux):**
```bash
sudo usermod -aG docker $USER   # then log out and back in
```

**Start over from a clean slate:**
```bash
docker compose down -v          # removes data + generated secrets
docker compose up
```
