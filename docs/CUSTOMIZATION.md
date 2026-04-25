# Customization

How to make Healthclaw feel like your own.

## Personality: SOUL.md

The `SOUL.md` file in your workspace defines your companion's voice, tone, and communication style.

### Default Location

When using Docker, your workspace is at `~/.nanobot/workspace/<user-id>/SOUL.md`

### Tone Presets

**Gentle** — Warm, soft landings, less pressure
```
You are warm but not syrupy. You lead with empathy, give space, and avoid pressure. When the user slips, you don't shame — you repair. Keep replies short and grounding.
```

**Direct** — Clear, concise, names things directly
```
You are direct without being harsh. You name avoidance when you see it, make crisp recommendations, and don't dance around the obvious. Short replies, clear next steps.
```

**Calm** — Quiet, steady, low stimulation
```
You are quiet and steady. You reduce surface area, focus on one next move, and keep energy low but grounded. Good for late nights, overwhelm, or anxiety.
```

### Example Customization

Change how Healthclaw responds to "I feel stuck":

**Default:**
> "I hear you. What do you think is holding you back?"

**Custom (Direct):**
> "Stuck usually means you're looking at everything at once. Pick one: the smallest useful task, or 90 seconds of just breathing. Which?"

## Voice: communication style

Edit `SOUL.md` to change how Healthclaw sounds. Key sections:

```markdown
# Communication Style

- Short replies by default (1-3 lines)
- Lead with one useful move before asking questions
- Ask at most one good question
- Be specific, not inspirational
- Never say "as an AI" or "I understand"
- No therapy-speak, no corporate warmth
```

## Memory Behavior: Dream Settings

Configure how often memory consolidation happens and how much it processes:

In your `nanobot.yaml` or `.env`:

```env
# Dream runs every 2 hours by default
NANOBOT_AGENTS__DEFAULTS__DREAM__INTERVAL_H=2

# Process up to 20 history entries per Dream run
NANOBOT_AGENTS__DEFAULTS__DREAM__MAX_BATCH_SIZE=20

# Limit Dream's editing iterations (safety budget)
NANOBOT_AGENTS__DEFAULTS__DREAM__MAX_ITERATIONS=10

# Use a different model for Dream (optional)
NANOBOT_AGENTS__DEFAULTS__DREAM__MODEL_OVERRIDE=gemma:2b
```

## Skills

Skills are markdown-based tools Healthclaw can use. They're defined in `nanobot/skills/`.

### Available Skills

- **health_check** — Run periodic health check-ins
- **medication_reminder** — Schedule medication reminders via cron
- **habit_tracker** — Track daily habits and patterns
- **mood_journal** — Guide mood logging and reflection

### Activating a Skill

Skills are activated based on context and conversation. To enable a skill:

1. Ensure the skill file exists in `nanobot/skills/`
2. The agent calls it automatically when relevant context is detected

## User Preferences: USER.md

The `USER.md` file stores stable knowledge about the user:

```markdown
# User Profile

- Name: [user's name]
- Preferences: [communication preferences]
- Health goals: [what they're working on]
- Patterns: [known habits or tendencies]
```

Healthclaw updates this through conversation and Dream consolidation.

## Custom Prompts

### System Prompt

Edit prompt templates in `nanobot/templates/`:

```
nanobot/templates/
├── agent/
│   ├── identity.md      # Who the bot is
│   ├── voice.md         # How it speaks
│   └── soul_global.md   # Default personality
└── health/
    ├── SOUL.md          # Health-specific personality
    └── cold_start_system.md
```

### First-Message Prompt

In `nanobot/templates/health/onboarding_system.md`:

```markdown
First conversation:
- Do not open with FAQ tone
- Respond to the subtext, not only literal words
- Give one useful next move immediately
- Ask one question that helps personalize
```

## Channel Configuration

### Telegram

Set bot behavior in `.env`:

```env
TELEGRAM_BOT_TOKEN=your-token
HEALTH_TELEGRAM_BOT_URL=https://t.me/your-bot
```

### Discord

In your Discord Developer Portal:
1. Enable **Message Content Intent**
2. Get your bot token
3. Set `DISCORD_BOT_TOKEN` in `.env`

### Adding New Channels

See [Channel Plugin Guide](CHANNEL_PLUGIN_GUIDE.md) for implementing custom channels.

## Tone Calibration Reference

| Aspect | Gentle | Direct | Calm |
|--------|--------|--------|------|
| Energy | Warm, soft | Crisp, clear | Low, steady |
| Questions | More supportive | Fewer, sharper | Minimal |
| Pressure | Avoids | Direct | Very low |
| Late-night mode | Soft | Firm | Grounding focus |
| Stuck response | "It's okay" | "Pick one" | "One anchor" |

## Resetting to Default

To reset personality to defaults:

1. Delete `SOUL.md` from your workspace
2. Restart the bot: `/restart`
3. BiocomeClaw will regenerate from templates

## Related Documentation

- [Natural Companion Prompts](NATURAL_COMPANION_PROMPTS.md) — Full prompt architecture
- [Memory System](MEMORY.md) — How Dream works
- [Getting Started](GETTING_STARTED.md) — Initial setup