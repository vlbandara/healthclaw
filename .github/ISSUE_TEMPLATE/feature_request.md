name: Feature Request
description: Suggest a new feature or improvement
title: "[Feature] "
labels: ["enhancement"]
assignees: []
body:
  - type: markdown
    attributes:
      value: |
        ## Feature Request

        Have an idea for how to make Healthclaw better? We'd love to hear it.

  - type: textarea
    id: problem
    attributes:
      label: Problem or Use Case
      description: |
        Describe the problem you're solving or the use case you're enabling.
        Why is this important to you?
    validations:
      required: true

  - type: textarea
    id: solution
    attributes:
      label: Proposed Solution
      description: |
        How would you like to see this problem solved? Describe the feature,
        behavior, or change you'd like.
    validations:
      required: true

  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives Considered
      description: |
        What other approaches have you considered? What trade-offs did you weigh?
    validations:
      required: false

  - type: textarea
    id: additional
    attributes:
      label: Additional Context
      description: Mockups, examples, references, or anything else
    validations:
      required: false