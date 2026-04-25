# Health Demo Runbook

This runbook is for local rehearsal of the Telegram health demo before any push.

## Goal

Use a seeded returning-user workspace that already contains:

- a known Telegram user
- a remembered sleep and training goal
- a prior voice-note style interaction
- one open loop for proactive follow-up
- proactive opt-in enabled

## Prerequisites

- `HEALTH_VAULT_KEY` is set
- `GROQ_API_KEY` is set for voice transcription
- a Telegram bot token is available for local testing

## Seed A Demo Workspace

```bash
uv run python scripts/health/seed_demo_workspace.py \
  --workspace /tmp/nanobot-health-demo \
  --force
```

The seed data lives in `[examples/health/demo_fixture.json](../examples/health/demo_fixture.json)`.

## Local Rehearsal Flow

1. Start from the seeded workspace and the health config template.
2. Use Telegram only for the demo surface.
3. Send a short returning-user opener like "Morning. What do you remember about where I left this?"
4. Send a voice note about sleep drift or stress. The expected behavior is:
   - transcript handled as a normal user message
   - no file paths, tool traces, or transcription internals in chat
   - one calm next step plus at most one question
5. Leave the bot idle long enough for proactive behavior. The expected behavior is:
   - no late-night nudge during quiet hours
   - at most one contextual autonomy push in a local day
   - proactive outreach only when opt-in or open-loop context exists

## Fast Checks

- `health/profile.json` should show `proactive_enabled=true`, `voice_preferred=true`, and a non-empty `last_seen_local_date`
- `USER.md` should contain goals, friction points, and communication preferences
- `memory/MEMORY.md` should contain lifecycle state plus `Last open loop`
- `sessions/telegram_demo-telegram-chat.jsonl` should contain prior assistant variation tags but no `reasoning_content`
- `memory/history.jsonl` should contain only user-visible summaries

## Demo Acceptance

The local demo is ready when all of the following are true:

- replies are calm, concise, and useful
- continuity is visible without sounding creepy or overfitted
- local time changes the reply style in obvious ways
- voice notes work through Groq without leaking internals
- proactive behavior feels deliberate rather than random
