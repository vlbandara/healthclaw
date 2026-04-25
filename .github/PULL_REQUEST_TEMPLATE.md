name: Pull Request
description: Submit changes to Healthclaw
title: "[PR] "
labels: []
assignees: []
body:
  - type: markdown
    attributes:
      value: |
        ## Pull Request

        Thank you for contributing to Healthclaw! Please fill out this checklist.

  - type: textarea
    id: description
    attributes:
      label: Description
      description: Summary of changes (what and why)
    validations:
      required: true

  - type: textarea
    id: testing
    attributes:
      label: Testing
      description: |
        How did you test your changes?
        - [ ] Tested locally with Ollama
        - [ ] Tested with cloud API
        - [ ] Ran `pytest tests/`
        - [ ] Tested in Docker Compose
    validations:
      required: true

  - type: textarea
    id: screenshots
    attributes:
      label: Screenshots (for UI changes)
      description: |
        If your change affects the UI, include before/after screenshots
        or screen recordings.
    validations:
      required: false

  - type: checkbox
    id: docs
    attributes:
      label: Documentation
      options:
        - label: Updated relevant docs in `/docs/`
        required: false

  - type: checkbox
    id: lint
    attributes:
      label: Lint Check
      options:
        - label: Ran `ruff check nanobot/` with no errors
        required: false

  - type: textarea
    id: breaking
    attributes:
      label: Breaking Changes
      description: |
        Does this PR introduce any breaking changes?
        If yes, describe what and how to migrate.
    validations:
      required: false

  - type: textarea
    id: additional
    attributes:
      label: Additional Notes
      description: Anything else reviewers should know
    validations:
      required: false