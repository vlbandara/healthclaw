## Summary

Describe what changed and why.

## Testing

- [ ] `uv run --extra dev ruff check nanobot tests`
- [ ] `uv run --extra dev pytest -q`
- [ ] `uv build`
- [ ] `uv run healthclaw doctor --env-file .env.local`
- [ ] `cd bridge && npm ci && npm run build && npm audit --audit-level=critical`

## Compatibility

- [ ] Public branding remains correct as **Healthclaw**
- [ ] Any retained `nanobot` runtime identifiers are intentional and documented

## Docs

- [ ] Relevant docs were updated

## Notes

List migrations, breaking changes, or reviewer context if needed.
