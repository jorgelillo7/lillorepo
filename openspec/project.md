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
| `biwenger_tools` | `api` | [`auto-bid`](specs/biwenger_tools/auto-bid/spec.md), [`clausulazo-emergency`](specs/biwenger_tools/clausulazo-emergency/spec.md), [`clausulazo-recommendations`](specs/biwenger_tools/clausulazo-recommendations/spec.md), [`daily-digest`](specs/biwenger_tools/daily-digest/spec.md), [`offers-inbox`](specs/biwenger_tools/offers-inbox/spec.md), [`auto-pick-lineup`](specs/biwenger_tools/auto-pick-lineup/spec.md), [`team-analysis`](specs/biwenger_tools/team-analysis/spec.md) |
| `biwenger_tools` | `bot` | [`telegram-commands`](specs/biwenger_tools/telegram-commands/spec.md) → calls `api` |
| `biwenger_tools` | `scraper_job` | [`league-scraper`](specs/biwenger_tools/league-scraper/spec.md) (messages → Firestore, tabla justicia) |
| `biwenger_tools` | `web` | [`web-dataviz`](specs/biwenger_tools/web-dataviz/spec.md) on Cloud Run |
| `be_water` | `web` | [`water-similarity`](specs/be_water/water-similarity/spec.md), [`provenance`](specs/be_water/provenance/spec.md), [`aesan-registry`](specs/be_water/aesan-registry/spec.md), [`community`](specs/be_water/community/spec.md), [`catalog-sync`](specs/be_water/catalog-sync/spec.md), [`data-curation`](specs/be_water/data-curation/spec.md), [`photos`](specs/be_water/photos/spec.md), [`seo`](specs/be_water/seo/spec.md) |
| `chucknorris_bot` | `bot` | [`chuck-jokes`](specs/chucknorris_bot/chuck-jokes/spec.md) Telegram bot |
| `core` | — | [`http-retry`](specs/core/http-retry/spec.md), [`gemini-client`](specs/core/gemini-client/spec.md), [`telegram-sdk`](specs/core/telegram-sdk/spec.md), [`biwenger-session`](specs/core/biwenger-session/spec.md), [`biwenger-reads`](specs/core/biwenger-reads/spec.md), [`biwenger-writes`](specs/core/biwenger-writes/spec.md); JP/Firestore SDKs + domain models |

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

## The rules the platform runs inside

The Lloros League reglamento and Biwenger's own limits are **environment, not
behaviour** — nothing here implements them, but several capabilities are only
correct because of them. Recorded once so they are not rediscovered per module:

| Rule | Where it bites |
|---|---|
| **Squad size is a per-league Biwenger setting**, not a platform constant — commonly 16–25 depending on how many managers play, and Premium can cap it per position. Ours is not exposed by the API | The squad and market renderers must stay legible well past the draft's fifteen; verified at 25 rows, which is the top of the usual range |
| **Jornada única** — *"entregar puntos y abonos tras disputarse todos los partidos"* (reglamento 2.5.8) | A matchday is not final until every match in it is played. 2026/27 opened with a round spanning **twelve days**, so standings, prizes and points are provisional until it closes — and no lineup set on day one is right for the whole round |
| **Per-matchday prize money** (2.5.7): 75k per point, 500k per Once Ideal player, 100k for the MVP, paid automatically by Biwenger | Cash grows every matchday without anyone selling, which is the budget auto-bid and the clausulazo recommender read |
| **Captain must cost < 3M** (Biwenger hard cap) | Enforced in `lineup.py`; the draft ranks the best sub-3M starter accordingly |
| **15 players able to field some legal XI**, bench unconstrained; snake draft; prices frozen to the export day | The draft capability, `specs/biwenger_tools/draft/spec.md` |
| **Clauses freeze 24 h before a matchday's first kickoff** (Biwenger platform rule). Nobody can be claused in that window, in either direction, and it reopens once the round is under way | Cash has to be positive *before* the freeze, not during the round: the auto-bid and the clausulazo recommender both have a deadline nothing in the code knows about. Stated by the league owner from Biwenger's own behaviour — **not** read from the API, so it belongs with the assumptions in `STATUS.md` until something verifies it |
| **A "next matchday" is not the next number.** 2026/27 interleaves postponed rounds: with Jornada 3 active, the next round to be played is **Jornada 6**, and Jornada 4 follows it | Anything reasoning about "the next round" must take Biwenger's own `next`, never the round number or the array order. `season.rounds[]` is not chronological |

The full text lives in the league's reglamento document, not in this repo. When
an article changes, the row above changes with it — and so does whatever it
bites.

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
