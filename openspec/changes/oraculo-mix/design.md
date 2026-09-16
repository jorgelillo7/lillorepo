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

## The endpoint, called and measured

`GET https://server.analiticafantasy.com/api/v1/oraculo/140?sistema=biwenger-sofascore`
— no authentication, and `sistema` is a **required query parameter resolved
server-side**, which is exactly what the page routes cannot do.

Called once to establish feasibility. It answers `200` and, crucially, **echoes
the system back**, so a reader can verify rather than assume:

```
sistema     biwenger-sofascore
matchday    7  ·  "Jornada 7"
generatedAt 2026-09-16T15:06:01Z
modelTag    poisson-team-strength-v2
```

The numbers are Biwenger's, confirmed against the same players read from the
LaLiga-Fantasy pages:

| | page (LaLiga Fantasy) | API (`biwenger-sofascore`) |
|---|---|---|
| Ferran Jutglà | 7.38 | **3.60** |
| Ionut Radu | 6.28 | **4.92** |
| Marcos Alonso | 5.53 | **4.74** |

### What it settles

- **The lists arrive in the right system.** All eight `picks` — `chollos`,
  `goleadores`, `asistentes`, `capitanes` and the four positions — scored as
  Biwenger. This was the sharpest open question and it is gone.
- **The matchday is given, not computed.** Top-level `matchday` is
  authoritative; `rounds[]` carries `isCurrent` / `isFinished` / `hasLineups`
  per round. Note `isCurrent` marks the **upcoming** matchday (7 here), not the
  one just played.
- **Staleness is stamped.** `generatedAt` and `modelTag` replace the
  `updated_at` treatment this plan was going to invent.
- **`fixtures[].hasPrediction`** makes a half-filled round detectable.

### What it does not settle: coverage

**43 unique players in the whole response** — 39 across the eight lists, plus
24 `topPlayers` slots spread thinly (six of ten fixtures carry none yet).

This is a **highlights endpoint, not a projection list.** Most of a squad will
not appear in it. That kills the idea of it being the single source.

## Two sources, and each is the right one for its half

| Need | Route | Why |
|---|---|---|
| Points + `chance` **for every squad player** | `/biwenger/predicciones` (page) | 366 players, Biwenger-scored, `Allow: /` in robots |
| **List membership** | `/api/v1/oraculo/140?sistema=…` | The eight lists, in the right system |
| Matchday, staleness, `hasPrediction` | same API call | Given rather than derived |

The split is not a compromise. List membership is inherently a top-N signal —
39 players *is* the complete set of recommendations, not a sample of it — while
the projection has to cover whatever the squad happens to hold.

## Permission — decided, and the scope of that decision

`robots.txt` disallows `/api/`, and the terms of service prohibit
«extracción, recolección o minería de datos (data scraping) **sin autorización
expresa**».

The owner has read both and decided to proceed on the grounds that this is a
personal, non-commercial tool for a private league of eight, redistributing
nothing and competing with nobody. That is their call to make on their own
project, and it is recorded here rather than left implicit.

What follows from it, and is not optional:

- **The client identifies itself honestly.** A descriptive `User-Agent` with a
  contact address, never a copy of browser headers. The site keeps the ability
  to see, rate-limit or block this; nothing here hides from it. (There is
  nothing to copy in any case — the capture recorded one header, `priority`.)
- **One call per run, cached.** The model retrains hourly; reading more often
  than that gets nothing and costs someone else's bandwidth.
- **Ask anyway.** «Sin autorización expresa» is a default, not an absolute. A
  short mail describing what is read, how often and why converts this from
  tolerated to allowed, and is the only thing that makes it durable.

## How the data arrives (the page route)



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
