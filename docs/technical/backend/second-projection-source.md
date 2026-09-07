# A second projection source

**Status: parked, waiting on one answer — can Analítica Fantasy's data be read
programmatically, with permission.** Everything below is the plan for when it
can. Nothing here is built.

## Why

Every lineup, captain and clausulazo decision this project makes rides on one
number: Jornada Perfecta's `SCORE_SF`, read through `core/sdk/jp.py` and
maximised by `lineup.py`. One gameweek made the cost of that visible.

| | projection | real |
|---|---|---|
| Valverde | 565 | 3 |
| Chupe | 450 | **−3** |
| Catena | 443 | **−4** |
| Bretones | 303 | **−7** (captain, so −14) |

The squad JP rated **13 high / 0 medium / 1 low** scored 15 points. A rival
squad rated **8 high / 3 medium / 6 low** scored 93 — and its top scorer, by
some distance, was the player JP rated lowest in it: a goalkeeper projected 48
who scored 23.

The lesson is not "JP is wrong". It is that a **point estimate is an
expectation**, and a single gameweek is decided by events — goals, clean
sheets, cards, a rating that goes negative. Ranking by expectation is right
over a season and blind to the two things that decide a week: **minutes** (does
he start at all) and **spread** (safe four points, or a coin flip between
twelve and minus four).

## The decision: add, do not replace

JP stays the ranking backbone. It has our history, `lineup.py` is tuned on it,
and its `predict` payload is already understood down to the `updated_at`
staleness checks.

**What a second source buys is not a better number. It is two things one source
cannot give at any price:**

1. **Disagreement.** Two independent models agreeing is confidence; disagreeing
   is risk, and the disagreement is usually about minutes — the single biggest
   producer of a zero.
2. **Different primitives.** Analítica's Oráculo publishes *probability of
   starting*, *probability of at least one goal* and *of at least one assist*
   (team xG distributed across the probable eleven by shot volume). Those are
   distributions, not point estimates.

Averaging the two projections into one number is the **least** valuable thing
we could do with the second source: it slightly improves the expectation and
does nothing about the variance and the negatives, which is what actually cost
the gameweek above.

## Division of labour, if it lands

| Source | Job |
|---|---|
| JP `SCORE_SF` | the ranking backbone, unchanged |
| Probability of starting | a **gate** — below a threshold a player does not start our eleven, whatever his SF |
| Probability of goal / assist | the **captain**, chosen from the sub-3M pool where we currently have no signal at all |
| The two disagreeing | a flag on the daily digest: "these two rate this player very differently" |

The captain is where this matters most and where we help least today. The
league caps the captain at under 3M, so the pool is cheap players — rotation
risks in weak teams, the ones that go deeply negative. Doubling one of those is
a coin flip, and our tooling currently treats the choice as maximisation rather
than risk.

## Sequencing: shadow mode first

**Read it, log it, decide nothing with it.** For several gameweeks store, per
player: JP's number, the second source's numbers, and the actual Biwenger
points.

That answers, with our own data rather than one bad afternoon: which predicts
better, whether disagreement anticipates a blow-up, and whether probability of
an event picks a better captain than `SCORE_SF` does.

It is also read-only, cannot break the 09:00 digest, and makes the first real
change of behaviour an evidence-based one. Adding a source and trusting it
immediately would repeat the mistake this document exists to fix — being sold
out to one number, only now to two of them.

The logging is worth doing **even if the second source never arrives**: today
nothing anywhere records what was projected against what was scored, so "is JP
worth what we pay in decisions" has no answer. `provider_watch` logs vocabulary
surprises from the provider, not accuracy.

## What blocks it

No public API is documented. There is a mobile app, so an internal one exists —
and this repo has already done that once: `docs/technical/reverse-engineering/
frida-android-intercept.md` records how the JP token was captured from the
Android bundle.

The difference is that Analítica is somebody's product with its own terms.
**Ask first** (they publish a contact box). A one-line email costs nothing and
may save building on an endpoint that changes without notice, or that they
object to. Same instinct this project already applies to third-party delivery
channels: prefer the official route over the side door.

## Where the work actually goes, and it is not the HTTP call

**Identity matching.** `player_matching.py` already carries a hand-maintained
table reconciling Biwenger names with JP's — `vinicius jr` → `vini jr`,
`sancet` → `oihan sancet`, and a dozen more. A third naming universe multiplies
that surface.

There is a trap already installed that a second source would make worse:
`clausulazo_candidates.sf_of` returns 0 when the JP match fails, and
`filter_affordable` drops everything with `sf <= 0`. A data-availability
problem is dressed as a quality filter — an unmatched player silently
disappears as though he were bad. **A second source must be loud**: report what
did not match, never zero it in silence.

## Operational constraints

- **The SLO.** The 09:00 digest has a five-minute end-to-end budget. A second
  provider adds latency and a new failure mode: it must degrade to JP alone,
  loudly, and never block the digest.
- **Staleness.** JP stamps `updated_at` and we check it. Whatever we read from
  a second source needs the same treatment; a projection recomputed hourly is
  worth nothing if we read yesterday's copy.

## Open questions

- Is there a legitimate programmatic route at all? Everything above waits on it.
- What exactly does the payload expose — the three probabilities, or only what
  the web renders?
- Does its player identity carry a stable id, or only a display name?
