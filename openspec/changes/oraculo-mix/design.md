# Design — mixing Oráculo into the projection

## The constraint that shapes everything

Three routes, and **they do not share a scoring system**:

| Route | System | Points | `chance` | List flags |
|---|---|:-:|:-:|:-:|
| `/oraculo-fantasy/la-liga` | LaLiga Fantasy | ✅ | ✅ | ✅ `chollos`, `goleadores`, `asistentes`, `capitanes`, `porteros`, `defensas`, `centrocampistas`, `delanteros` |
| `/partido/{fixtureId}-{slug}` | LaLiga Fantasy | ✅ | ✅ | ✅ `isChollo`, `isCapitan`, `isAriete`, `isBufon`, `isRevulsivo` |
| **`/biwenger/predicciones`** | **Biwenger** | ✅ | ✅ | ❌ |

`?sistema=biwenger-sofascore` does not change the first two. The router reads
it — the payload carries `"q":"?sistema=biwenger-sofascore"` — but the props
holding the numbers still say `"sistema":"la-liga-fantasy"`, and the values
come back identical. The switch is applied client-side after hydration. Both
plausible path variants (`/oraculo-fantasy/biwenger-sofascore/la-liga` and the
reverse) return 404.

Measured, same players and matchday:

    Jutglà 7.38 → 2.06     Radu 6.28 → 4.08     Marcos Alonso 5.53 → 4.89

A source read through the wrong scoring system is the kind that looks like it
works and quietly poisons every decision. **The number must come from
`/biwenger/predicciones`.**

## The endpoint the second capture found

A later export, taken with the Oráculo page open, found what the first one
missed:

```
GET /api/v1/oraculo/140?sistema=<sistema>     # no authentication
```

`sistema` is a **required query parameter**, resolved server-side. That is
precisely what the page routes cannot do, and it collapses most of this design:

| Response field | What it settles |
|---|---|
| `sistema` | Echoed back, so a read can **verify** it got Biwenger and not assume it |
| `picks` | All eight lists — `chollos`, `goleadores`, `asistentes`, `capitanes`, `porteros`, `defensas`, `centrocampistas`, `delanteros` — in the requested system |
| `fixtures` | With `hasPrediction`, so a half-filled round is detectable rather than inferred |
| `rounds[]` | `isCurrent`, `isFinished`, `hasLineups`, `matchday` — "the next matchday" stops being a guess |
| `generatedAt`, `modelTag` | The staleness stamp this plan asks for, given rather than invented |

Each `picks` entry carries `playerId`, `slug`, `predictedPoints`, `chance`,
`goalProbability`, `assistProbability`, `pointsPerMillion`, `marketValue`,
`position`, `fixtureId`.

**One call replaces eleven page reads, and the lists arrive in the right
scoring system.** Open question 1 — "the list flags come from the wrong system"
— disappears entirely if this route is used.

### And it is the one route `robots.txt` forbids

```
Allow: /                 ← the pages: right data, wrong system
Disallow: /api/          ← this: right system, right lists, one call
```

So the technical question is now fully answered and the whole decision is a
permission one. Nothing in this repo calls it, and nothing should until that
question has an answer that is not a guess. The two designs below are kept
side by side because which one gets built depends entirely on it.

## How the data arrives (the allowed route)

Next.js App Router: everything is in the RSC flight payload embedded in the
public HTML (`self.__next_f.push([1, "..."])`). No API call, no cookie, no key.

Two fragile helpers isolate that — `_flight(html)` and `_objects(payload, key)`
— so a layout change breaks one test loudly instead of the whole service.

`/biwenger/predicciones` carries **two matchdays at once**, the one in play and
the one coming, separated by `fixtureDate`. "Always the next" is a filter, not
a URL to compute.

## The blend

JP ≈ 0-700, Oráculo ≈ 0-10. The scales are not comparable, so this is a
multiplier on JP and never an average.

```
base   = jp_sf                       # unchanged when Oráculo has no opinion
bonus  = 0.0

if   oraculo_points >= 6.0:  bonus += 0.30     # "looks good"
elif oraculo_points <= 3.0:  bonus -= 0.30     # "looks bad"

if   oraculo_chance >= 80:   bonus += 0.10     # near-certain starter
elif oraculo_chance <= 40:   bonus -= 0.20     # probably benched

if   oraculo_lists:          bonus += 0.10     # named in any recommended list

custom = round(base * (1 + clamp(bonus, -0.50, +0.50)))
```

**Every number above is a guess**, fitted to one worked case: JP has Jutglà at
500 and benched, Oráculo has him over 6.00 and likely to start, so he comes out
around 1.4× instead of losing his place to JP's read alone.

## Failure modes this must not repeat

- **A missing match is not a bad player.** `sf_of` returning 0 for a player JP
  does not carry once took the league ranking down. `oraculo_matched=False`
  means "no opinion" and must never read as "bad".
- **A third naming universe.** `playerId` is stable within Analítica, so
  matching goes through `player_matching.py` like JP — and a failure must be
  loud, never a silent zero.
- **Degrade loudly.** The 09:00 SLO says a second provider must fall back to JP
  alone and say so.
- **Scraping is not a contract.** The flight payload is a framework
  implementation detail. It will break without notice.

## Read time

A matchday fills in progressively: three days out, only 2 of 10 fixtures had
any projection at all, and 79 of 366 rows belonged to the upcoming round. **When
it is read decides what is in it.**
