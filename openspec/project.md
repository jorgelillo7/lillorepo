# Project — lillorepo

> The canonical, tool-agnostic map of this repository's *behaviour*, for any
> reader (human or AI agent) landing here cold. Structure and build details
> live in `CLAUDE.md`; this describes **what the system does and must keep
> doing**. Specs live in `openspec/specs/{package}/{capability}/spec.md` —
> grouped by the package they belong to, since a capability is meaningful only
> within its project.

## What this is

A Bazel monorepo of small Python services targeting Google Cloud, built around
a Biwenger (fantasy football) toolkit and a couple of independent side
projects. Every service is a Cloud Run app or Job; there is no shared runtime
state beyond Firestore and Google Secret Manager.

## Packages and their capabilities

| Package | Module | Capability spec (`specs/{package}/…`) |
|---|---|---|
| `biwenger_tools` | `api` | [`auto-bid`](specs/biwenger_tools/auto-bid/spec.md), [`clausulazo-emergency`](specs/biwenger_tools/clausulazo-emergency/spec.md), [`daily-digest`](specs/biwenger_tools/daily-digest/spec.md) |
| `biwenger_tools` | `bot` | Telegram command surface → calls `api` |
| `biwenger_tools` | `scraper_job` | [`league-scraper`](specs/biwenger_tools/league-scraper/spec.md) (messages → Firestore, tabla justicia) |
| `biwenger_tools` | `web` | [`web-dataviz`](specs/biwenger_tools/web-dataviz/spec.md) on Cloud Run |
| `be_water` | `web` | [`water-similarity`](specs/be_water/water-similarity/spec.md), [`provenance`](specs/be_water/provenance/spec.md), [`aesan-registry`](specs/be_water/aesan-registry/spec.md), [`community`](specs/be_water/community/spec.md), [`catalog-sync`](specs/be_water/catalog-sync/spec.md), [`data-curation`](specs/be_water/data-curation/spec.md), [`photos`](specs/be_water/photos/spec.md) |
| `chucknorris_bot` | `bot` | chuck-jokes Telegram bot |
| `core` | — | shared SDK contracts (Biwenger, JP, Firestore, Telegram, Gemini) + domain models |

## How behaviour is pinned

- **Specs** (`openspec/specs/{package}/{capability}/spec.md`) state the
  contract in prose + `Requirement`/`Scenario` form: the single source of
  *what must be true*.
- **Tests** (`packages/*/tests/`, `core/tests/`) are the executable
  verification of those specs. A scenario without a test is a gap; a test
  without a scenario is undocumented behaviour. Test docstrings link back to
  the spec section they verify.
- The relationship is complementary, not duplicated: the spec says **what**,
  the test proves **that it holds**.

## Service-level objective

One SLO covers the user-facing surface — the 09:00 Madrid daily digest,
end-to-end ≤ 5 min. It is stated as a requirement in
`specs/biwenger_tools/daily-digest/spec.md`; the rationale and accepted gaps
stay in `CLAUDE.md` / `STATUS.md`.

## Convention note

This folder follows the [OpenSpec](https://github.com/Fission-AI/OpenSpec)
filesystem convention (`specs/` = current behaviour, `changes/` = in-flight
proposals with `proposal.md` / `design.md` / `tasks.md` / spec deltas). We
adopt the **convention only** — the folder layout and the
`Requirement`/`Scenario` markdown format — without the global `npm` CLI, in
line with this repo's preference for vendored/scripted tooling over wrapper
installers. The `/opsx:*` slash commands are optional and not wired.
