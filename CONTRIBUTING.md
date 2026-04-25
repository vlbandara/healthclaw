# Contributing to Healthclaw

Thank you for being here.

Healthclaw is built with a simple belief: wellbeing tools should feel calm, clear, and personal.
We care deeply about useful features, but we also believe in achieving more with less:
solutions should be powerful without becoming heavy, and ambitious without becoming
needlessly complicated.

This guide is not only about how to open a PR. It is also about how we hope to build
software together: with care, clarity, and respect for the next person reading the code.

## Maintainers

| Maintainer | Focus |
|------------|-------|
| [@vlbandara](https://github.com/vlbandara) | Project lead, wellbeing companion |

## Branching Strategy

We use a simple model:

| Branch | Purpose |
|--------|---------|
| `main` | Stable releases |
| `nightly` | Experimental features |

### Which Branch Should I Target?

**Target `nightly`** if your PR includes:
- New features or functionality
- Refactoring that may affect existing behavior
- Changes to APIs or configuration

**Target `main`** if your PR includes:
- Bug fixes with no behavior changes
- Documentation improvements
- Minor tweaks that don't affect functionality

**When in doubt, target `nightly`.** Stable features are merged to `main` periodically.

## Development Setup

Setup should be boring and reliable:

```bash
git clone https://github.com/vlbandara/Healthclaw.git
cd Healthclaw

# Install with dev dependencies (uses uv)
pip install -e ".[dev]"

# Run tests
pytest

# Lint code
ruff check nanobot/

# Format code
ruff format nanobot/
```

## Good First Issues

Looking for a way to contribute? Look for the `good first issue` label on
[GitHub Issues](https://github.com/vlbandara/Healthclaw/issues?q=label%3A%22good+first+issue%22).

We label issues that are:
- Self-contained and well-scoped
- Have clear acceptance criteria
- Don't require deep knowledge of the codebase

## Code Style

We care about more than passing lint. We want Healthclaw to stay small, calm, and readable.

When contributing, please aim for code that feels:

- **Simple** — prefer the smallest change that solves the real problem
- **Clear** — optimize for the next reader, not for cleverness
- **Decoupled** — keep boundaries clean and avoid unnecessary new abstractions
- **Honest** — do not hide complexity, but do not create extra complexity either
- **Durable** — choose solutions that are easy to maintain, test, and extend

In practice:

- Line length: 100 characters (`ruff`)
- Target: Python 3.11+
- Linting: `ruff` with rules E, F, I, N, W (E501 ignored)
- Async: uses `asyncio` throughout; pytest with `asyncio_mode = "auto"`
- Prefer readable code over magical code
- Prefer focused patches over broad rewrites
- If a new abstraction is introduced, it should clearly reduce complexity rather than move it around

## Questions?

If you have questions, ideas, or half-formed insights, you are warmly welcome here.

- [GitHub Discussions](https://github.com/vlbandara/Healthclaw/discussions) — Ask questions, share ideas
- [GitHub Issues](https://github.com/vlbandara/Healthclaw/issues) — Report bugs, request features

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## Acknowledgements

Healthclaw is a wellbeing-focused fork of [nanobot](https://github.com/HKUDS/nanobot) by the HKUDS team.
We're grateful for their excellent foundation.

Thank you for spending your time and care on Healthclaw. We would love for more people to participate in this community, and we genuinely welcome contributions of all sizes.