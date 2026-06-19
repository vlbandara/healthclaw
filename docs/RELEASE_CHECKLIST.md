# Release Checklist

Use this before publishing an open-source Healthclaw self-host beta release.

## Secrets

- Rotate any provider key, Telegram token, or bridge token that appeared in logs, screenshots, chat, or raw compose output.
- Confirm `.env`, `.env.local`, `.env.prod`, and generated state directories are not tracked.
- Use `healthclaw doctor` for diagnostics instead of sharing raw `docker compose config`.

## Validation

```bash
uv run --extra dev ruff check nanobot tests
uv run --extra dev pytest -q
uv build
uv run healthclaw init-local --env-file .env.local.test --force
uv run healthclaw doctor --env-file .env.local.test
cd bridge && npm ci && npm run build && npm audit --audit-level=critical
```

Remove `.env.local.test` after validation.

## Public Surface

- README and site describe Healthclaw as a self-host beta.
- Hosted multi-tenant claims are not in headline copy.
- WhatsApp is hidden unless explicitly marked experimental.
- Local links do not reference `/Users/...` paths.
- Kubernetes examples do not use `ghcr.io/your-org/nanobot`.

## Safety

- The repo states Healthclaw is wellbeing support, not a medical device.
- Emergency and crisis copy points users to local urgent services.
- Open Wearables remains optional and does not imply diagnosis or treatment.
