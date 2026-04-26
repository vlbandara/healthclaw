# Changelog

All notable changes to Healthclaw are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-04-26

### Added

- Public stable-beta release surface for **Healthclaw**
- public docs for getting started, self-hosting, architecture, customization, and FAQ
- open-source community files: code of conduct, contributing guide, issue templates, and changelog
- onboarding, observability, storage, and health-mode platform work shipped on this branch

### Changed

- clarified that Healthclaw is a **fork of nanobot**
- kept `nanobot` package, CLI, paths, and `NANOBOT_*` env vars for v0.2 compatibility
- simplified GitHub Actions to public CI only
- removed private-infrastructure deployment/monitoring material from the public release surface
- cleaned lint and packaging so the public repo ships with green quality gates

### Security

- replaced stale security contact details
- kept secrets out of examples and public automation

### Acknowledgements

Healthclaw is built on [nanobot](https://github.com/HKUDS/nanobot) by HKUDS.
