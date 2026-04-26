# Contributing to Healthclaw

Healthclaw is a public fork of [nanobot](https://github.com/HKUDS/nanobot), focused on privacy-first wellbeing companions.

The public product name is **Healthclaw**.
For v0.2 compatibility, the runtime identifiers still use `nanobot` in code, CLI, and environment variables.

## Workflow

- Branch from `main`
- Keep changes focused
- Open pull requests back into `main`
- Document behavior changes, config changes, and compatibility impact clearly

## Local Setup

```bash
git clone https://github.com/vlbandara/healthclaw.git
cd healthclaw
uv sync --all-extras
```

Useful commands:

```bash
uv run ruff check nanobot tests
uv run pytest -q
uv build
docker compose config
cd bridge && npm ci && npm run build
```

## Contribution Standards

- Prefer small, reviewable patches over broad rewrites.
- Keep public docs aligned with actual runtime behavior.
- Preserve `nanobot` compatibility unless the change intentionally migrates it.
- Add or update tests when behavior changes.
- Avoid committing local state, secrets, screenshots, or generated artifacts unless they are intentionally part of the product.

## Public Surface Rules

When editing public-facing materials:

- refer to the product as **Healthclaw**
- state clearly when something is inherited from or compatible with `nanobot`
- use the canonical repository URL: `https://github.com/vlbandara/healthclaw`

## Questions

- [GitHub Discussions](https://github.com/vlbandara/healthclaw/discussions)
- [GitHub Issues](https://github.com/vlbandara/healthclaw/issues)

Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before participating.
