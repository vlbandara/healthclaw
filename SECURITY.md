# Security Policy

## Reporting a Vulnerability

Please do **not** open public issues for security reports.

Use one of these private channels:

1. GitHub Security Advisories / private vulnerability reporting on this repository
2. If that is unavailable, contact the maintainer privately through GitHub at [@vlbandara](https://github.com/vlbandara)

Include:

- affected version or commit
- impact summary
- reproduction steps or proof of concept
- any suggested mitigation

Target response times:

- initial acknowledgement within 72 hours
- status update within 7 days

## Scope

This repository is the public **Healthclaw** fork of `nanobot`.
The public branding is Healthclaw, but some runtime identifiers still use `nanobot` for compatibility in v0.2.

Please report issues affecting:

- the Python application and API
- channel integrations
- Docker and deployment assets in this repository
- build, packaging, or release automation
- the TypeScript WhatsApp bridge under `bridge/`

## Security Basics for Operators

- Never commit real `.env` files, tokens, or provider credentials.
- Restrict channel access with explicit allow-lists before public exposure.
- Run the stack as a dedicated non-root user where possible.
- Keep `~/.nanobot` protected because it may contain chat history, auth state, and workspace data.
- Prefer HTTPS for public deployments and keep reverse-proxy exposure limited to intended ports.
- Review dependency advisories regularly for both Python and Node.js dependencies.

## Supported Release Posture

Healthclaw v0.2 is a **public stable beta**.
It is intended for self-hosting, experimentation, and contribution.
It is not represented as a hardened medical or regulated production system.
