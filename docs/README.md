# docs/ — index

One entry per document. Runbooks first, then setup, then deep dives.

## Operations & infrastructure

| Doc | What's in it |
|---|---|
| [`operations.md`](operations.md) | The runbook: per-module commands (run, test, deploy), dependency workflow, secrets, cleanup scripts, season rollover, Firestore maintenance |
| [`gcp.md`](gcp.md) | GCP services in use and the *rationale* behind every cost decision; cross-project deploy grants (see also [`INFRA.md`](../INFRA.md) at the repo root for the at-a-glance inventory) |
| [`firestore.md`](firestore.md) | Firestore data model: collections, doc shapes, indexes, TTLs |

## Setup

| Doc | What's in it |
|---|---|
| [`setup/mac-setup.md`](setup/mac-setup.md) | Dev machine bootstrap (bazelisk, gcloud, Python) |
| [`setup/linter.md`](setup/linter.md) | flake8 + black configuration and editor wiring |
| [`setup/ai/claude-code-setup.md`](setup/ai/claude-code-setup.md) | Claude Code config for this repo (skills, hooks, memory) |
| [`setup/ai/mcp-setup.md`](setup/ai/mcp-setup.md) | MCP servers |
| [`setup/ai/rtk-setup.md`](setup/ai/rtk-setup.md) | rtk token-optimizing CLI proxy |
| [`setup/ai/google-skills.md`](setup/ai/google-skills.md) | Google Cloud skills sync (`scripts/sync-google-skills.sh`) |
| [`setup/ai/pi-setup.md`](setup/ai/pi-setup.md) | Pi, the minimal multi-provider terminal coding harness: install and config |

## Technical deep dives

| Doc | What's in it |
|---|---|
| [`technical/backend/python-best-practices.md`](technical/backend/python-best-practices.md) | Python standards guide (PEP 8/20 + team experience) |
| [`technical/reverse-engineering/frida-android-intercept.md`](technical/reverse-engineering/frida-android-intercept.md) | How the JP token was captured (Frida + Android JS bundle); scripts alongside |
| [`technical/migration/retrofit-patterns.md`](technical/migration/retrofit-patterns.md) | Legacy-modernisation patterns (Strangler Fig, Branch by Abstraction…) |
| [`technical/ai/claude-code-roadmap.md`](technical/ai/claude-code-roadmap.md) | Claude Code adoption roadmap for this repo |
| [`technical/ai/claude-code-director-workflow.md`](technical/ai/claude-code-director-workflow.md) | Director-mode workflow notes |
| [`technical/ai/ralph-wiggum-methodology.md`](technical/ai/ralph-wiggum-methodology.md) | Autonomous-loop methodology notes |

## External APIs

| Doc | What's in it |
|---|---|
| [`external/biwenger-api.yaml`](external/biwenger-api.yaml) | Reverse-engineered Biwenger API (OpenAPI) |
| [`external/jp-api.md`](external/jp-api.md) | Jornada Perfecta private API notes |

## Elsewhere in the repo

- [`README.md`](../README.md) — project overview and architecture
- [`STATUS.md`](../STATUS.md) — living maturity report
- [`INFRA.md`](../INFRA.md) — GCP inventory at a glance
- [`PENDING.md`](../PENDING.md) — long-running follow-ups
- `packages/*/release-notes.md` — per-package history
- [`docs/project_pitch.md`](project_pitch.md) — the original pitch
