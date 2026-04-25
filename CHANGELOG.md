# Changelog

All notable changes to Healthclaw are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-25

### Added

- **Open Source Launch** — Healthclaw is now publicly available as an open-source project
- **Local Gemma Support** — First-class support for running Google Gemma locally via Ollama, enabling fully private deployments
- **Family Multi-Tenant Mode** — Each family member gets their own isolated Docker workspace with separate memory, config, and health profile
- **CODE_OF_CONDUCT.md** — Contributor Covenant v2.1 community guidelines
- **CHANGELOG.md** — This changelog file for tracking releases
- **ROADMAP.md** — Public roadmap for the project
- **GitHub Issue Templates** — Bug report, feature request, and question templates
- **GitHub PR Template** — Pull request checklist for contributors
- **Getting Started Guide** — [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) — Step-by-step beginner walkthrough
- **Architecture Documentation** — [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — System design deep dive
- **Customization Guide** — [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) — Personality, tone, and skills
- **FAQ** — [docs/FAQ.md](docs/FAQ.md) — Common questions about privacy, hardware, and setup
- **Self-Hosting Guide** — [docs/SELF_HOSTING.md](docs/SELF_HOSTING.md) — Deploy on any VPS

### Changed

- **README Rewrite** — Complete rewrite positioning Healthclaw as a private wellbeing companion with local-first story as primary path
- **CONTRIBUTING.md Rewrite** — Rewritten for Healthclaw's own contributor identity
- **pyproject.toml** — Updated project metadata: description, keywords, and project URLs for PyPI
- **COMMUNICATION.md** — Replaced HKUDS references with Healthclaw community links
- **docker-compose.yml** — Added comments for newcomer clarity

### Security

- **Secrets Protection** — `.env.example` now has clear warnings about never committing real API keys

### Acknowledgements

Healthclaw is a wellbeing-focused fork of [nanobot](https://github.com/HKUDS/nanobot) by the HKUDS team. We're grateful for their excellent foundation.

---

## [0.1.5] - 2026-04-24

Previous nanobot release history would be documented here.