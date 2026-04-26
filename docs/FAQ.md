# FAQ

Common questions about Healthclaw.

## Privacy & Security

### Is my data sent anywhere?

**Local setup (Ollama + Gemma):** No. All conversations stay on your machine. Your data never leaves your home.

**Cloud API setup:** Your conversations are sent to the AI provider you choose (OpenRouter, Anthropic, OpenAI, etc.). Check their privacy policies. We don't store or log your conversation content.

### How does family isolation work?

Each family member gets their own isolated Docker container with separate:
- Memory files (SOUL.md, USER.md, MEMORY.md)
- Conversation history
- Health profile

Data never crosses between containers. Even if you're using the same Telegram bot, Healthclaw routes each user to their own private workspace.

### Are my health reminders secure?

Health data is encrypted in the health vault using Fernet encryption. Secrets are stored in environment variables and never committed to git.

---

## Hardware & Performance

### What hardware do I need?

| Setup | RAM | GPU | Notes |
|-------|-----|-----|-------|
| Gemma 2B | 4GB | Optional | Good for testing |
| Gemma 7B | 8GB | Optional | Recommended |
| Gemma 27B | 16GB+ | Recommended | Best quality |

GPU significantly speeds up inference but isn't required. Gemma 7B runs on CPU in 10-20 seconds per response.

### Can I run this on a Raspberry Pi?

Not recommended for production. The memory requirements and inference speed make it impractical. Use a VPS or dedicated machine instead.

### How fast is Ollama?

Depends on your hardware:
- **With GPU:** 50-200 tokens/second
- **CPU only (Gemma 7B):** 5-15 tokens/second

Cloud APIs are faster but cost money and send data externally.

---

## Setup & Configuration

### Why use Docker?

Docker provides:
- Isolated workspaces per user (multi-tenancy)
- Consistent environment across machines
- Easy dependency management
- Simple deployment and updates

The alternative (bare metal) requires manually managing Python dependencies and is not recommended for multi-user setups.

### Can I use Healthclaw without Docker?

Yes, but:
- Single-user mode only
- Manual dependency installation
- No family multi-tenancy

For local dev without Docker, see [docs/LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md).

### Do I need a Telegram bot?

No. Telegram is the default and easiest channel, but you can use:
- Discord
- Slack
- WhatsApp (via bridge)
- Matrix
- Email

See [Channel Plugin Guide](CHANNEL_PLUGIN_GUIDE.md) for setup.

---

## Models & Providers

### Why Gemma via Ollama?

Gemma is Google's open-weight model. Running it locally via Ollama means:
- 100% private (no data leaves your machine)
- No API costs
- Works offline
- No rate limits

It's the recommended path for privacy-conscious users.

### Can I use a different model?

Yes. Ollama supports many models:
```bash
# Llama
ollama pull llama3

# Mistral
ollama pull mistral

# Custom models
ollama pull [model-name]
```

Then set in `.env`:
```env
NANOBOT_AGENTS__DEFAULTS__MODEL=llama3
```

### What's the difference between providers?

| Provider | Privacy | Speed | Cost |
|----------|---------|-------|------|
| Ollama (local) | ✅ 100% | Medium | Free |
| OpenRouter | ⚠️ Third-party | Fast | Pay-per-use |
| Anthropic | ⚠️ Third-party | Fast | Pay-per-use |
| OpenAI | ⚠️ Third-party | Fast | Pay-per-use |

---

## Memory & Continuity

### How does Dream work?

Dream runs periodically (default: every 2 hours) and:
1. Reads new entries from `history.jsonl`
2. Compares with existing long-term memory (SOUL.md, USER.md, MEMORY.md)
3. Makes surgical edits to keep memory coherent

It doesn't rewrite everything — only the smallest honest change.

### Can I see what Dream changed?

Yes. Use `/dream-log` to see the latest change. Use `/dream-log <sha>` to see a specific change.

### Can I undo a Dream change?

Yes. Use `/dream-restore <sha>` to restore memory to before a specific change. The SHA is shown in `/dream-log`.

### What is history.jsonl?

An append-only log of compressed conversation summaries. Cursor-based, optimized for machine consumption. You can search it with grep or jq.

---

## Troubleshooting

### Ollama not responding

```bash
# Check if Ollama is running
curl http://localhost:11434

# Restart Ollama
ollama serve

# Check running models
ollama list
```

### Bot not responding on Telegram

1. Verify `TELEGRAM_BOT_TOKEN` is correct in `.env`
2. Check logs: `docker compose logs worker | tail -50`
3. Restart: `docker compose restart worker`

### Docker permission issues (Linux)

```bash
# Add yourself to docker group
sudo usermod -aG docker $USER
# Log out and back in
```

### Can't add family members

Ensure `NANOBOT_MULTI_TENANT=true` is set in your `.env`. Each new user needs to message the bot once to trigger workspace creation.

---

## Miscellaneous

### Is Healthclaw a medical device?

No. Healthclaw is for educational and wellbeing purposes. It is not a medical device and is not a substitute for professional healthcare. For health concerns, consult a medical professional.

### Can I self-host on a VPS?

Yes. See [Self-Hosting Guide](SELF_HOSTING.md) for a complete walkthrough.

### How do I update Healthclaw?

```bash
git pull
docker compose --env-file .env up -d --build
```

### Where do I get help?

- [GitHub Discussions](https://github.com/vlbandara/healthclaw/discussions) — Ask questions
- [GitHub Issues](https://github.com/vlbandara/healthclaw/issues) — Report bugs
- [CONTRIBUTING.md](../CONTRIBUTING.md) — How to contribute

---

## Still have questions?

Open a [GitHub Discussion](https://github.com/vlbandara/healthclaw/discussions) or [GitHub Issue](https://github.com/vlbandara/healthclaw/issues/new/choose). We're happy to help.
