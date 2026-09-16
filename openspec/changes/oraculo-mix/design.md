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
| Points + `chance` **for every squad player** | `/biwenger/predicciones` (page) | Biwenger-scored, `Allow: /` in robots — but see the coverage note below |
| **List membership** | `/api/v1/oraculo/140?sistema=…` | The eight lists, in the right system |
| Matchday, staleness, `hasPrediction` | same API call | Given rather than derived |

The split is not a compromise. List membership is inherently a top-N signal —
39 players *is* the complete set of recommendations, not a sample of it — while
the projection has to cover whatever the squad happens to hold.

### Coverage is a function of *when*, not of the route

`/biwenger/predicciones` returns 366 rows, and that number is misleading: they
span **two matchdays at once**, and most belong to the one being played rather
than the one coming. Measured three days out from J7:

| | rows with a projection > 0 |
|---|---|
| J6 (16-17 Sept, imminent) | 252 |
| **J7 (19-20 Sept, the one we want)** | **67** |

319 of the 366 carry a non-zero projection at all; 327 carry a starting
`chance`. The tail is real — the site itself paginates to 366 and the last
entries read `Esperado 0.00` at 20% titularidad.

So the usable figure is not 366 and not 319: it is **whatever the next matchday
has been filled in with at the moment of reading**, which was 67 at three days
out and rises as kickoff approaches. `fixtureDate` filtering is not an
optimisation, it is the thing that makes the number mean anything.

This makes the read-time question (open question 3) quantitative rather than a
matter of taste: a Tuesday read covers a fraction of the squad, a Saturday
morning read covers most of it. Note also that `fixtures[].hasPrediction` was
`true` for all ten J7 fixtures while only 67 players had numbers — the fixture
flag means the model has an opinion on the *match*, not that its players are
projected yet.

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

## The blend — calibrated against a real squad

**JP is the base and stays the base.** Oráculo is a second opinion that nudges
it; it never replaces it and never decides alone.

### The first formula was wrong, and the data says why

The original proposal used absolute thresholds — "≥ 6.0 looks good, ≤ 3.0 looks
bad". Those came from the **LaLiga Fantasy** scale, where Jutglà reads 7.38.
Biwenger's scale runs much lower: the same player is 3.60.

Checked against a real 14-man squad (Cebollitas, J7), only **Mbappé** clears
6.0, and four of thirteen fall below 3.0. The formula would have marked most of
a decent squad as "looks bad".

**Any absolute threshold on this number is a bug waiting for a scale change.**

### Self-calibrating instead

Convert Oráculo to JP's scale using the **median ratio of the rows in that very
read**, so there is no constant to get wrong and it survives either provider
rescaling:

```
k      = median(jp_sf / oraculo_points)   over covered rows   # ≈ 105 observed
equiv  = oraculo_points * k                                   # Oráculo, in JP units
custom = round(jp_sf * (1 - W) + equiv * W)                   # W ≈ 0.30
```

Measured on the 13 covered players, the spread of `jp_sf / oraculo_points` was
**37 to 210** with a median of 105 — which is the point: the two disagree
wildly on individuals while agreeing on the population. That disagreement is
the entire value of a second opinion, and a weighted average keeps it bounded.

| | JP | Oráculo → JP | custom (W=0.30) | Δ |
|---|---|---|---|---|
| Mbappé | 892 | 777 | 857 | −4% |
| Fermín | 688 | 413 | 606 | −12% |
| Aubameyang | 654 | 327 | 556 | **−15%** |
| Hancko | 351 | 351 | 351 | 0% |
| Jon Martín | 381 | 526 | 425 | **+12%** |
| Terrats | 354 | 510 | 401 | **+13%** |
| Redondo | 103 | 294 | 160 | **+55%** |

JP loves Aubameyang and Oráculo does not; Oráculo likes Redondo, Jon Martín and
Terrats considerably more than JP. Those five rows are what this whole change
is for.

### `chance` is probably already inside the number

On the API, `expectedPoints == predictedPoints × chance`, exactly. The
`/biwenger/predicciones` page labels its column **"Esperado"**, so its number is
very likely post-`chance` already — and adding a further `chance` bonus would
double-count it.

So `chance` is **a guard, not a bonus**: below a floor (say 25%) damp the
Oráculo contribution toward zero, because a number built on a player who
probably will not play should not move JP's. Above it, do nothing.

### Everything here is still a guess

`W = 0.30` and the 25% floor are fitted to one squad on one matchday. They go
in env vars, tunable without a deploy.

## The goal and assist probabilities belong to the captain, not the blend

`goalProbability` and `assistProbability` exist **only in `picks`** — 38
players — and not in `/biwenger/predicciones`, which carries the 472 rows. So
they cannot feed the blend: most of a squad would have no value and the ones
that did would move for a reason nobody else's row shared.

They are also **different information**. `predictedPoints` is an expectation;
these two are the shape of the distribution behind it. Measured on the same
matchday, both under 3M:

| | points | goal | assist |
|---|---|---|---|
| Pedro Díaz | **5.85** | 3.9% | 2.4% |
| Marcos Fernández | 3.98 | **21.1%** | 11.6% |

Pedro Díaz scores more on average. Marcos Fernández has five times the ceiling.
For a starter that difference barely matters — the eleven is a sum, and a sum
wants expectation.

**For the captain it is the whole question.** Captaincy doubles the return, so
it pays for the tail rather than the mean, and `_pick_captain` already reasons
this way: it refuses a promoted substitute because "starting him is a bet with
the bench as insurance; captaining him doubles the bet and has none."

The coverage lines up too. Biwenger caps the captain at a 3M market value, and
**14 of the 38 `picks` players are under it** — the captain is always drawn
from a short list, which is exactly the shape this signal comes in.

### Measured: the points only half-absorb the goals

The obvious objection is that goals are where the points come from, so the
probability is already inside `predictedPoints` and using it again would
double-count. Correlated across the 32 picks players that carry both:

| | vs `predictedPoints` |
|---|---|
| `goalProbability` | **r = +0.50** |
| `assistProbability` | r = +0.11 |

| by position | n | mean goal prob | r |
|---|---|---|---|
| Delantero | 12 | 0.232 | +0.56 |
| Centrocampista | 11 | 0.098 | +0.18 |
| Defensa | 9 | 0.037 | +0.10 |

r = 0.50 means the points explain about **a quarter** of the variation in goal
chance (r² = 0.25). Three quarters of it is information the points ordering
does not carry — so it is not redundant, and for defenders and midfielders it
is almost entirely independent.

That settles the objection in favour of using it. What it does not settle is
*where*: the signal exists for 38 players, so it still cannot be a term in a
blend that has to rank a whole squad without promoting whoever Oráculo happened
to look at.

So: `predictedPoints` drives the blend for everyone, and the probabilities feed
`_pick_captain` alone — the one decision whose candidate list is already short,
and the one where the tail is worth more than the mean. Deliberately a separate
phase: the blend must be working before the captain starts arguing with it, and
revisiting them for the eleven is a real option once there is a season of
evidence about how often the 38 overlap a squad.

## Falling back to JP — three levels, not one

The brief is "if it fails for any reason we keep JP". That failure arrives in
three different shapes and each needs its own answer.

### 1 · Per player — no opinion

Oráculo does not carry this player, or carries him with no projection.
`custom == jp_sf`. Nothing marked: this is the normal state for most of a
squad most of the week.

### 2 · Per read — too thin to use at all

**This is the Wednesday case, and it is the one worth getting right.** Three
days out the upcoming matchday held 67 projected players against a league of
~500, so a squad of twenty would expect two or three opinions.

A *partial* blend is worse than none. Three players get a 1.3× boost and
seventeen do not, so those three jump the queue for no reason except that
Oráculo happened to have looked at their fixture first. The ranking stops
meaning anything and nobody can see why.

So it is all-or-nothing, per read:

```
covered = rows with an Oráculo projection / rows being scored
if covered < ORACULO_MIN_COVERAGE:   # 0.60 to start, a guess to calibrate
    blend off for this whole read, and say so
```

### 3 · Per source — unreachable or wrong

Timeout, HTTP error, unparseable payload, or **the echoed `sistema` is not the
one asked for**. Blend off, log loudly, and say so. The SLO already demands
this: a second provider must degrade to JP alone and never block the digest.

A wrong `sistema` counts as a failure rather than a warning. Reading LaLiga
Fantasy numbers while believing they are Biwenger's is the one outcome worse
than having no second opinion at all.

## Saying so — the marker

Levels 2 and 3 are invisible unless the output says so, and an unmarked
fallback is how a silent regression lives for months.

`/analizar` and `/mercado` photos: the `Proyección` column header becomes
**`Proyección (JP)`** and the title carries a suffix. Text first, colour
second — `image_formatter`'s own rule is that shape carries the meaning and
the hue reinforces it, so a red tint alone would not do.

Telegram text surfaces (`/recomendar`, `/emergencia`, `/ofertas`) carry one
line: *"⚠️ Solo JP — Oráculo no disponible"* or *"…sin datos suficientes"*,
distinguishing level 3 from level 2 because they call for different reactions:
one is broken, the other is just early in the week.

## Every reader, and there are more than four

The first draft of this plan listed four. A full sweep of what consults JP
found **seven**, and one of them spends money:

| Reader | What it decides | Kind |
|---|---|---|
| `lineup._sf` | the starting eleven, applied unattended every morning | decision |
| `clausulazo_candidates.sf_of` | `/recomendar` + all three `/emergencia` pools | decision |
| `auto_bid` | what to bid on | decision |
| **`offers.py`** | **accept or reject an incoming offer** | **decision** |
| `image_formatter` | the `Proyección` column in every photo | display |
| `league_compare` | the league-wide squad ranking | display |
| `actions.py` / `player_formatting` | row rendering for `/analizar`, `/mercado` | display |

`offers.py` reads `get_predict_rate(..., 2)` directly in two places to value an
incoming offer. It was missed because it does not go through `sf_of`, and it is
the one place a wrong number costs money immediately rather than points on
Sunday.

Pass-throughs that need no change: `rows.py` (where the join goes),
`orchestration.py` (where the fetch goes), `digests.py`, `player_matching.py`.
Out of scope: the draft skill and `postdraft.py`, which are annual and run off
exported CSVs.

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

## Read time — decided

**One read per execution, cached an hour**, the same shape `core/sdk/jp.py`
already uses.

### The numbers move a lot within a day

Measured six hours apart on the same matchday and the same fixture: Mbappé's
expectation went **11.46 → 7.39**, Vini Jr **6.0 → 2.79**. That is the model
reacting to lineup news, not noise.

And coverage moves with it. The upcoming matchday went from **67** projected
players at 15:00 to **260** at 21:00 the same day.

Matchdays normally start **Friday 20:00**, and Biwenger locks lineup changes at
the first kick-off. So the useful window closes then, and the **Friday 09:00
digest is the natural best read** — latest data, still changeable. Anything
read after the first match cannot change a lineup and is only worth having for
the market and the clausulazo surfaces. The model retrains hourly, so reading more often buys nothing and
spends someone else's bandwidth.

A midweek read simply falls under the coverage threshold and marks itself
JP-only. That is the correct outcome rather than a compromise: the alternative
designs — skipping the fetch entirely when kickoff is far, or moving the lineup
tick to Saturday — both add a rule to maintain in exchange for an outcome the
threshold already produces.

### The thresholds must be tunable without a deploy

There is no shadow week, so every guessed number goes live as written. They
belong in env vars the way `LINEUP_SUB_STARTS_ABOVE` already is — and that
precedent carries a warning: its default read 350 while production ran 300 for
months, so the backlog spent that time asking about a number nobody executed.
**The default in the code must be the value that runs.**

## Read time (superseded note)

A matchday fills in progressively: three days out, only 2 of 10 fixtures had
any projection at all, and 79 of 366 rows belonged to the upcoming round. **When
it is read decides what is in it.**
