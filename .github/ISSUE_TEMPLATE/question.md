name: Question
description: Ask a question or get help
title: "[Question] "
labels: ["question"]
assignees: []
body:
  - type: markdown
    attributes:
      value: |
        ## Question

        Need help with something? We're happy to assist.

        Before posting, check the [FAQ](docs/FAQ.md) and [docs](https://github.com/vlbandara/Healthclaw#documentation) to see if your question is already answered.

  - type: textarea
    id: question
    attributes:
      label: Your Question
      description: Be as specific as possible
    validations:
      required: true

  - type: textarea
    id: context
    attributes:
      label: Context
      description: |
        What have you already tried? What's your setup?
        (OS, deployment method, Healthclaw version, etc.)
    validations:
      required: false

  - type: textarea
    id: logs
    attributes:
      label: Relevant Logs
      description: Paste any error messages or relevant output (remove sensitive data)
    validations:
      required: false