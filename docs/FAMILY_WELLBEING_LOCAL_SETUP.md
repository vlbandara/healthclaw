# Family Wellbeing Companion Setup (Local + Private)

Healthclaw is architected from the ground up to isolate contexts. This means you can onboard your entire family into the system using a single host, and **each family member will securely receive their own private assistant container** with no memory bleed between them. 

Coupled with Google's localized Gemma model via Ollama, this provides a highly private, subscription-free, family-scale setup.

## Prerequisites

1. **Docker and Docker Compose** installed.
2. **Ollama** installed on your host machine to serve models locally.

## 1. Setup Ollama (Host Machine)

Install Ollama from [ollama.com](https://ollama.com/) if you haven't already.
Run the Gemma model. For an ideal balance of speed and intelligence, we recommend `gemma:7b`, but `gemma:2b` is great for smaller resource pools:

```bash
ollama run gemma:7b
```

## 2. Configure Healthclaw Environment

Create your local `.env.local` directly from the template:

```bash
cp .env.local.example .env.local
```

Open `.env.local` in your text editor. We need to ensure multi-tenancy is active and point it to our local Ollama instance hook. Adjust these variables:

```env
# Enable multiple family members
NANOBOT_MULTI_TENANT=true

# Route AI tasks to Ollama natively via Docker's host hook
NANOBOT_AGENTS__DEFAULTS__PROVIDER=ollama
NANOBOT_AGENTS__DEFAULTS__MODEL=gemma:7b
OLLAMA_API_BASE=http://host.docker.internal:11434
```

> **Note for Linux hosts**: If `host.docker.internal` doesn't resolve defaultly on your Linux distribution, append `--add-host=host.docker.internal:host-gateway` in your docker-compose or change the base to `http://172.17.0.1:11434`.

## 3. Connect Channels (e.g., Telegram)

Set up a single Telegram bot using BotFather as described in [TELEGRAM_BOTFATHER_SETUP.md](./TELEGRAM_BOTFATHER_SETUP.md), and map your Bot Token into your `.env.local`:

```env
TELEGRAM_BOT_TOKEN=123456789:YOUR_TOKEN_HERE
```

## 4. Run the Stack

Execute Healthclaw's local development stack right from the directory:

```bash
LOCAL_DEV=1 docker compose --env-file .env.local up -d --build postgres redis orchestrator worker whatsapp-bridge
```

## 5. Onboarding the Family

Have each family member search for your bot's username on Telegram and send a message. Since `NANOBOT_MULTI_TENANT=true` is enabled:

1. **Family Member A** says "Hi" -> Healthclaw Orchestrator spins up an isolated Docker workspace and database partition solely for Member A.
2. **Family Member B** says "Hi" -> Healthclaw spins up a completely separate, pristine workspace. 

Neither member can see, access, or bleed into the other's memories. Everything is processed against your private Gemma Ollama node seamlessly.
