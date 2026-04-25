name: Bug Report
description: Report something that isn't working correctly
title: "[Bug] "
labels: ["bug"]
assignees: []
body:
  - type: markdown
    attributes:
      value: |
        ## Bug Report

        Thank you for reporting a bug. Please fill out the sections below to help us understand and fix the issue.

        **Healthclaw version:** (run `nanobot --version` or check your Docker image tag)

  - type: textarea
    id: environment
    attributes:
      label: Environment
      description: |
        Describe your setup (OS, Python version, Docker version, deployment method)
        Examples: Ubuntu 22.04, Python 3.12, Docker Compose on Hetzner VPS
    validations:
      required: true

  - type: textarea
    id: steps
    attributes:
      label: Steps to Reproduce
      description: |
        Exact steps to reproduce the bug. Be specific and numbered.
        Example:
        1. Run `docker compose up -d`
        2. Send "Hi" to the Telegram bot
        3. Ask for medication reminder
        4. See error in logs
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected Behavior
      description: What should happen
    validations:
      required: true

  - type: textarea
    id: actual
    attributes:
      label: Actual Behavior
      description: What actually happens
    validations:
      required: true

  - type: textarea
    id: logs
    attributes:
      label: Relevant Logs
      description: |
        Paste relevant log output (remove any sensitive information)
        Use ``` to format as code
    validations:
      required: false

  - type: textarea
    id: additional
    attributes:
      label: Additional Context
      description: Screenshots, versions, anything else that helps
    validations:
      required: false