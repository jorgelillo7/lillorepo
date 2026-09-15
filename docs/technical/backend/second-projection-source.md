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

## What the page actually serves — read, not captured

The first capture hunted for an API endpoint and found only configuration and
fixtures. That was the wrong place to look: **Analítica does not fetch these
numbers, it ships them.** The site is Next.js App Router, so the data arrives
inside the RSC flight payload embedded in the public HTML
(`self.__next_f.push([1, "..."])`). No API call, no cookie, no key — a plain
`GET` of the page a visitor sees.

`robots.txt` draws the line in exactly the place that matters:

```
Allow: /                 ← the pages below
Disallow: /api/          ← the endpoint the first capture was hunting
```

The route that works is allowed; the route that was being chased is the one
explicitly off-limits. That is a crawler directive, not a licence — the terms
of service are a separate question and the owner's to answer.

### The scoring system is the whole ballgame

`/oraculo-fantasy/la-liga` is the page a human lands on, and reading it is a
trap. Its numbers are **LaLiga Fantasy**, not Biwenger.

`?sistema=biwenger-sofascore` does not fix it. The router receives the
parameter — the payload carries `"q":"?sistema=biwenger-sofascore"` — but the
props that hold the numbers say `"sistema":"la-liga-fantasy"` either way, and
the values come back identical. The switch is applied client-side after
hydration. Path variants (`/oraculo-fantasy/biwenger-sofascore/la-liga` and the
reverse) both 404.

How much it matters, same players, same matchday:

| | `/oraculo-fantasy` | `/biwenger/predicciones` |
|---|---|---|
| Ferran Jutglà | 7.38 | **2.06** |
| Ionut Radu | 6.28 | **4.08** |
| Marcos Alonso | 5.53 | **4.89** |

A source read through the wrong scoring system is the kind that looks like it
works and quietly poisons every decision. `SCORE_SF` is SofaScore-based; the
left column is not.

### The route that answers

**`/biwenger/predicciones`** is server-rendered, Biwenger-scored, and needs no
parameter. Checked against a screenshot of the site taken independently:
Marcos Alonso 4.89 against 4.99, Carl Starfelt 4.20 against 4.29 — within the
hourly retrain. Per player it carries:

`playerId` · `slug` · `playerName` · `position` · `positionId` ·
`playerTeamId` · `chance` (starting probability) · `predictedPoints` ·
`isEstimate` · `fixtureId` · `fixtureDate` · `homeTeamName` · `awayTeamName`

`playerId` and `slug` answer the identity question: there is a stable id, so
this is the same matching problem `player_matching.py` already solves — with
the same trap, that **a failed match must be loud and never a silent zero**.

### Coverage, measured

366 players in one read, spanning two matchdays at once — the one being played
and the one coming — separated by `fixtureDate`. So "always the next matchday"
is a filter, not a URL to compute.

The catch is that a matchday fills in progressively. Three days out, 79 of
those 366 belonged to the upcoming round, and on the Oráculo pages only 2 of
10 fixtures had any projection at all. **When it is read decides what is in
it**; a Saturday-morning read is a different dataset from a Tuesday one.

## What is still open

- **Terms of service.** `robots.txt` permits these pages; that is not a licence.
  Reading them for a private league of eight is a different act from
  redistributing them, and the distinction is the owner's to make before any of
  this ships.
- **Staleness.** The model retrains hourly and the numbers visibly move. Read
  as late as the 09:00 SLO allows, and stamp what was read.
- **Scraping is fragile by nature.** The flight payload is a framework
  implementation detail, not a contract. It will break without notice, and the
  SLO says it must degrade to JP alone, loudly.

## Open questions

Both of the original ones are answered above: the payload exposes a starting
probability and a points projection, and identity carries a stable `playerId`.
What replaces them is narrower — the scoring system, the read time, and
permission.
