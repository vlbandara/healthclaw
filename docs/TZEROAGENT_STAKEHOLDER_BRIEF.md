# BiomeClaw Stakeholder Brief

## Overview

**BiomeClaw** is a health-focused conversational companion designed to help people stay consistent with sleep, routines, training, recovery, and everyday health behaviors. The product is built around one core premise: real value comes from continuity, not just intelligence.

The current live demo is available at [https://tzeroagent.online](https://tzeroagent.online), with Telegram as the primary interaction channel.

This document is written for an early stakeholder or first customer evaluating whether BiomeClaw is a credible product direction and a worthwhile pilot opportunity.

## The Problem

Most health and wellness products break down in one of three ways:

- they collect data but do not translate it into timely behavioral support
- they offer chat, but the conversation is generic and forgetful
- they rely on human touchpoints that do not scale between sessions

Users do not need more dashboards. They need a companion that can maintain context over time, understand what they are trying to change, and show up in a useful way when the timing matters.

The real gap is not information. The real gap is follow-through.

## Product Thesis

BiomeClaw is being built as a private conversational layer for health behavior support.

The assistant should:

- remember the user's goals, routines, friction points, and prior commitments
- respond differently in the morning, at night, or after a long lapse
- support the user with a grounded and calm tone instead of synthetic enthusiasm
- handle text and voice updates naturally
- take a lightweight proactive role when appropriate
- operate in a way that feels personal without feeling invasive

The product is not intended to replace clinical care. It is intended to improve consistency, engagement, and momentum around behavior change.

## What BiomeClaw Is Today

The current version is a hosted demo of a private AI health companion.

Current status:

- live public demo at [https://tzeroagent.online](https://tzeroagent.online)
- Telegram onboarding and chat are in scope
- web landing and setup flow are live
- fresh demo environment with no legacy users
- dedicated production deployment on Hetzner
- isolated per-user runtime architecture
- persistent memory and continuity system in place
- voice-note support available through Groq transcription

Current non-goals for this demo:

- WhatsApp is not required for acceptance
- this is not positioned as a diagnosis or treatment system
- this is not yet a broad multi-channel commercial release

## Experience Principles

The current product direction is guided by a few strict principles.

### 1. Continuity Over Novelty

The assistant should feel like it remembers the user in a reliable way. It should not start from zero every day, and it should not sound like it is improvising a personality from scratch each turn.

### 2. Value First

The assistant should provide useful help quickly. Especially early in a relationship, the conversation should prioritize clarity, emotional steadiness, and one practical next step.

### 3. Calm, Grounded Tone

The system is being tuned away from sarcasm, social testing, suspicion, and cleverness for its own sake. Stable trust matters more than edge.

### 4. Time Awareness

Responses should account for the user's timezone, part of day, quiet hours, and interaction gaps so the same message is handled differently at 7am and 1am.

### 5. Controlled Proactivity

Proactive behavior should feel deliberate. The system should not spam, over-message, or intrude during quiet hours.

### 6. Privacy Through Isolation

Each user's workspace, memory, and runtime context are kept isolated. This is not only an implementation detail; it is part of the product trust model.

## What Makes The Product Different

BiomeClaw is differentiated less by raw model access and more by the system wrapped around the model.

### Layered Memory

The product uses multiple layers of memory for different kinds of continuity:

- operational profile facts
- durable user context
- relationship state and open loops
- summarized user-visible conversation history

This allows the assistant to retain useful continuity without treating every message as equal.

### Hosted Onboarding

Users can move from landing page to setup flow to Telegram-based conversation without a developer-style setup process. This matters because the first customer is evaluating an actual user journey, not a lab experiment.

### Per-User Isolation

Each user gets an isolated workspace and runtime environment, which is stronger than a typical shared-prompt chatbot architecture.

### Runtime Time Context

The system derives time-aware context such as local date, weekday, part of day, quiet hours, and re-engagement gap to influence reply behavior.

### Voice As Conversation Input

Voice notes can be transcribed and treated as a normal user utterance, enabling more natural check-ins for users who do not want to type.

### Constrained Proactive Layer

The system can support reminders and contextual nudges, but in a bounded way that respects quiet hours and recent activity.

## Why This Can Matter Commercially

BiomeClaw can create value in several adjacent models:

- a premium consumer health companion
- an add-on for coaching or behavior-change programs
- a retention and engagement layer for wellness services
- a private branded companion for high-touch health or fitness offerings

The strongest near-term business value is likely:

- higher user retention
- more frequent engagement between formal touchpoints
- a stronger feeling of personalization
- a product experience that is harder to replicate with a generic LLM wrapper

## Ideal First Customer Profiles

The best first customer is likely not a large institution. It is likely a focused operator with a clear user outcome and willingness to pilot.

Best-fit profiles:

- an independent coach or coaching business
- a wellness program with recurring member engagement needs
- a premium fitness, recovery, or lifestyle brand
- an early-stage digital health product looking for differentiated support between check-ins

The best pilot use cases are narrow, measurable, and high-frequency.

Examples:

- sleep consistency support
- training adherence support
- nutrition habit follow-through
- daily accountability for a coaching cohort

## Demo Scope For Stakeholders

The best live demo is not a broad feature tour. It is a compact story that demonstrates trust, continuity, and usefulness.

Recommended flow:

1. Show the landing page at [tzeroagent.online](https://tzeroagent.online).
2. Show the setup flow and Telegram connection path.
3. Start the conversation with a returning-user style prompt.
4. Demonstrate that the assistant remembers prior context.
5. Show a voice note or voice-note transcript flow.
6. Show a calm late-night or anxious-message response.
7. Show how the assistant follows an open loop rather than starting over.

What the stakeholder should notice:

- the assistant sounds coherent and steady
- the assistant recalls context without sounding creepy
- the timing of the response feels appropriate
- the response is concise and actionable
- the product feels like a system, not just a model

## Technical Credibility

The product is already running as a real hosted deployment rather than a slideware prototype.

Key deployment characteristics:

- deployed on Hetzner
- public domain configured at `tzeroagent.online`
- TLS-enabled hosted access
- fresh demo reset with no inherited user state
- production compose stack with orchestrator, worker, Postgres, Redis, and edge proxy
- diagnostic and rollback backups created during deployment cutover

This matters because a first customer is not only evaluating the concept. They are evaluating whether the team can operationalize it.

## Trust, Safety, And Boundaries

The product should be presented with clear boundaries.

- BiomeClaw is not a medical device.
- It should not be framed as diagnosis, treatment, or prescribing.
- Sensitive conversations require calmness, discretion, and non-judgment.
- Internal traces, hidden reasoning, temp paths, and system internals should never surface in user chat.

A serious health companion must be useful without pretending to be clinical authority.

## Current Readiness

For a first stakeholder review, the product is in a credible demo state.

Ready now:

- hosted setup and onboarding flow
- Telegram-based demo experience
- persistent memory and continuity
- voice-note handling path
- time-aware response behavior
- fresh public deployment

Still to refine after stakeholder feedback:

- deeper pilot-specific workflows
- stronger analytics for user retention and behavior outcomes
- broader channel support if commercially required
- packaging for a customer-branded rollout

## Proposed Pilot Structure

The most credible next step after stakeholder interest is a narrow pilot.

Suggested structure:

- choose one target user segment
- choose one primary behavior-change problem
- run a defined pilot cohort or founder-led test
- measure engagement, repeated use, and subjective trust
- refine the assistant behavior around one high-value workflow before expanding scope

Examples of pilot success indicators:

- repeat conversations over multiple days
- voice-note usage by real users
- reduced drop-off after onboarding
- positive user sentiment around "it remembers me" and "it helps when I need it"

## Suggested Executive Narrative

If this is presented live or converted into slides, the most effective narrative is:

- health products have a continuity problem
- generic AI does not solve that on its own
- BiomeClaw is a continuity-first health companion
- the current demo proves hosted onboarding, memory, timing, and practical coaching
- the right next step is a focused first-customer pilot

## Closing

BiomeClaw should be understood as a serious attempt to build a trustworthy, private, continuity-driven health companion. The live system at [tzeroagent.online](https://tzeroagent.online) is not just a conversational demo. It is an early product surface that demonstrates how onboarding, memory, timing, and action-oriented support can work together in a real deployment.

For a first customer, the question is not whether AI chat exists. The question is whether this product can become a meaningful layer in user behavior change and long-term engagement. BiomeClaw is now at the stage where that question can be tested credibly.
