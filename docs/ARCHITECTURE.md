# Architecture

This document describes how Healthclaw is structured and how data flows through the system.

## High-Level Overview

```
┌─────────────────────────────────────────────────────┐
│                   Telegram / Channels                │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  Healthclaw Gateway                   │
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

## Components

### Gateway

The gateway is the main entry point. It:
- Accepts messages from channels (Telegram, Discord, etc.)
- Routes them to the appropriate user workspace
- Handles authentication and session management
- Coordinates with the AI provider

### Channels

Channels are how users communicate with Healthclaw:

| Channel | Protocol | Notes |
|---------|----------|-------|
| Telegram | Bot API | Requires bot token from @BotFather |
| Discord | WebSocket | Requires bot token + Message Content intent |
| Slack | Socket Mode | No public URL needed |
| WhatsApp | WebSocket bridge | QR code login |
| Matrix | Homeserver API | Access token based |
| Email | IMAP/SMTP | Polls inbox, sends responses |

Adding a new channel is done by implementing the channel plugin interface.

### Providers

Providers abstract the AI backend:

| Provider | Model Support | Notes |
|----------|--------------|-------|
| `ollama` | Gemma, Llama, Mistral, any Ollama model | **Recommended** for local/private |
| `openrouter` | Any model accessible via OpenRouter | Unified API for many providers |
| `anthropic` | Claude family | Direct API |
| `openai` | GPT-4, GPT-4o | Direct API |
| `deepseek` | DeepSeek models | Direct API |
| `groq` | Llama, Mixtral | Free tier available |
| `vllm` / `ovms` | Any OpenAI-compatible | Local server |
| `custom` | Any OpenAI-compatible endpoint | Bring your own |

### Agent

The agent is the core reasoning loop. It:
1. Takes the user message
2. Loads relevant memory and context
3. Constructs a prompt using SOUL.md and templates
4. Calls the AI provider
5. Returns the response through the channel

### Memory System

Healthclaw uses layered memory:

```
┌─────────────────────────────────────────────────────┐
│                    Session                           │
│              (live conversation)                    │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              History (history.jsonl)                 │
│         (compressed, append-only archive)           │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                    Dream                              │
│         (periodic consolidation + reflection)         │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│           Long-Term (SOUL.md, USER.md, MEMORY.md)     │
│              (durable, curated knowledge)            │
└─────────────────────────────────────────────────────┘
```

**Session** — Current conversation context, in-memory

**History** (`memory/history.jsonl`) — Append-only compressed archive of past conversations. Cursor-based, optimized for machine consumption.

**Dream** — Periodic consolidation that:
- Reads new history entries
- Compares with existing long-term memory
- Makes surgical edits to SOUL.md, USER.md, MEMORY.md
- Does not rewrite everything, only the smallest honest change

**Long-Term** — Durable knowledge files:
- `SOUL.md` — Bot's voice and communication style
- `USER.md` — User's identity, preferences, stable facts
- `MEMORY.md` — Project facts, decisions, durable context

### Per-User Workspace

Each user (or family member) gets an isolated workspace:

```
workspace/<user-id>/
├── SOUL.md              # Bot's voice for this user
├── USER.md              # User's profile and preferences
└── memory/
    ├── MEMORY.md        # User's durable knowledge
    ├── history.jsonl    # Compressed conversation archive
    ├── .cursor          # Consolidator write cursor
    ├── .dream_cursor    # Dream consumption cursor
    └── .git/            # Version history for memory files
```

The workspace is stored in a dedicated Docker container, keeping data fully isolated between users.

## Multi-Tenancy

When `NANOBOT_MULTI_TENANT=true`:

1. User sends "Hi" → Gateway creates a new isolated Docker workspace
2. Each user has their own container with separate:
   - Memory files
   - Health profile
   - AI context
   - Configuration

No data crosses between workspaces. Family members cannot see each other's conversations or memory.

## Data Flow: Message Received

```
1. Channel (Telegram) receives message
         ↓
2. Gateway validates and routes to user workspace
         ↓
3. Agent loads:
   - SOUL.md (bot personality)
   - USER.md (user context)
   - Recent history
   - Channel-specific templates
         ↓
4. Agent constructs prompt and calls AI provider (Ollama/Cloud)
         ↓
5. Response is returned through the channel
         ↓
6. Message added to session history
         ↓
7. Dream periodically consolidates → updates long-term memory
```

## Key Files and Directories

```
nanobot/
├── agent/           # Core agent logic
│   ├── context.py    # Prompt assembly
│   └── memory.py     # Memory operations
├── channels/         # Channel implementations
│   ├── telegram.py
│   ├── discord.py
│   └── ...
├── providers/       # AI provider integrations
│   ├── ollama.py
│   ├── openrouter.py
│   └── ...
├── health/          # Wellbeing-specific logic
│   ├── worker.py
│   ├── orchestrator.py
│   └── ...
├── templates/       # Prompt templates
│   ├── agent/
│   └── health/
└── skills/          # Skill definitions (markdown-based)
```

## Security Notes

- Each workspace runs in an isolated Docker container
- Secrets are stored in the health vault, encrypted with Fernet
- Family mode ensures zero data leakage between users
- Local Ollama setup means no data ever leaves your machine

## Related Documentation

- [Memory System](MEMORY.md) — Detailed memory architecture
- [Natural Companion Prompts](NATURAL_COMPANION_PROMPTS.md) — How the voice works
- [Channel Plugin Guide](CHANNEL_PLUGIN_GUIDE.md) — Adding new channels
- [Security](SECURITY.md) — Production security checklist