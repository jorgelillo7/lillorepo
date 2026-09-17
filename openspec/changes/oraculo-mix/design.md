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

### The clamp, and why running it on a real squad found it

A weighted average pulls the extremes toward the population median. Run against
the owner's own sixteen, that showed up immediately:

    Fortuño   JP 12  ·  Oráculo 0.74  ·  k=131   →  37   (+212%)

A backup keeper Jornada Perfecta scores at 12 — "will not play" — becomes 37
purely by existing in Oráculo's feed. Nothing about him got better; the formula
simply drags anything far below the median upward.

`ORACULO_MAX_MOVE = 0.25` caps how far the blend can move any player:

| | JP | unclamped | clamped |
|---|---|---|---|
| Fortuño | 12 | 37 (+212%) | **15 (+25%)** |
| Rioja | 78 | 55 (−30%) | 58 (−25%) |
| Bretones | 302 | 275 (−9%) | 275 (−9%) |
| Dmitrovic | 404 | 447 (+11%) | 447 (+11%) |
| Valverde | 561 | 524 (−7%) | 524 (−7%) |

The property that matters: **it only bites on the outliers.** Everyone in the
body of the distribution comes out identical, so the clamp costs nothing where
the blend was already sensible.

The original bonus-ladder draft had `clamp(bonus, -0.50, +0.50)` and it was
lost in the move to a weighted average — the two are algebraically the same
(`jp*(1-W) + eq*W == jp*(1 + W*(eq/jp - 1))`) and only one of them made the
bound obvious.

It changes no decision *today*: both 12 and 37 sit far below every threshold
`lineup` compares against, so the eleven is identical either way. It is worth
fixing anyway, because a number that inflates 212% is one nobody can trust when
it does start deciding something — and it would be printed in the photo.

### Calibrated, and still tunable

Chosen against the real squad with the numbers in front of the owner rather
than guessed:

| | value | why |
|---|---|---|
| `ORACULO_W` | **0.30** | Moves enough for disagreement to mean something without letting one odd read reorder the squad. Fermín −18%, Jon Martín +12%, Hancko untouched |
| `ORACULO_MIN_COVERAGE` | **0.60** | 9 of 14 is enough to blend. Coverage was 79% a day and a half out and far lower on Tuesday, so this switches on when the data is real and off when it is not |
| `ORACULO_LIST_BONUS` | **0.03** | Capped at three lists, so +9% maximum — below the ±18% the blend moves. A mark is a hint, not a verdict |
| `CHOLLO_MARGIN` | **150K** flat | On a ~1.1M chollo that is a 1.25M bid: weak on purpose |
| chollo synthetic SF | **300** | The bare minimum to clear `auto_bid`'s skip, so they queue behind every real signing |
| `ORACULO_MAX_MOVE` | **0.25** | Caps the blend's movement either way. Only bites on outliers — see above |

All env-tunable without a deploy, the way `LINEUP_SUB_STARTS_ABOVE` is — and
the default in the code must be the value that runs, since that exact drift
has bitten once already.

The measured constant `k` is **113** today (median `jp_sf / oraculo_points`),
and it is deliberately not a setting: it recalculates per read so neither
provider rescaling can break it.

## One number, and the lists go into it

The projection field carries everything: JP as the base, the Oráculo blend when
there is data, and a bonus for the shortlists a player appears on. One column to
read, one number to argue with.

An earlier draft kept the lists out of the score on the grounds that they cover
38 players of ~500. That reasoning was wrong, and the distinction is worth
keeping straight:

- The **points** coverage is arbitrary — it depends on which fixtures the model
  has processed yet, which is why a partial blend distorts and is all-or-nothing.
- The **lists** are not arbitrary. They are a deliberate top-N: being on one is
  information, and being absent from one is the normal state of 92% of players,
  not a gap in the data.

So a list bonus is a real signal rather than noise, and stacking it is right —
the players on three or four lists are exactly the ones you would expect
(Aubameyang, Raphinha, Mbappé, Bellingham, Vini Jr., Lamine Yamal).

    lists per player:   1 → 24 · 2 → 8 · 3 → 4 · 4 → 2

### But not every list belongs in a points number

Measured on one matchday:

| | mean price | mean points |
|---|---|---|
| `chollos` | **1.1M** | **4.10** |
| every other list | 7.0M | 5.10 |

**`chollos` ranks value, not quality.** Its players are cheap and score *less*,
and only 2 of its 10 also appear on a best-per-position list. Adding a points
bonus for it would promote cheap players in the eleven, where price is
irrelevant — the exact mistake the draft optimiser already makes with cameo
totals.

So `chollos` feeds **bid priority**, where price is the whole point, and never
the projection.

`capitanes` looks derived rather than independent — every 3-and-4-list player is
on it — so it is excluded as double-counting until something shows otherwise.

### The plus

```
qualifying = goleadores · asistentes · porteros · defensas ·
             centrocampistas · delanteros          (chollos and capitanes out)

custom = blended * (1 + LIST_BONUS * min(len(qualifying), 3))   # 0.03 to start
```

Capped at three so the bonus stays secondary to the blend, which moves ±15%.
Mbappé on three qualifying lists gets +9%; a single-list player +3%.

### Three columns, not one

The photos show the inputs beside the output, so the formula is arguable
without leaving Telegram:

    Jugador      Pos  Precio   JP   Oráculo   Proyección    Racha  Juega
    Mbappé       DEL   24.9M  892   7.4 ★★    ▌▌▌▌▌ 883      10    fuera
    Aubameyang   DEL   13.6M  654   3.8 ★★★   ▌▌▌▌  573      14    casa
    Hancko       DEF    4.0M  351   3.3       ▌▌▌▌  351       3    casa
    Iturbe       POR    0.1M   12   —         ▌      12       0    suplente

`Proyección` keeps the bar and stays the number every decision uses. `JP` and
`Oráculo` are raw, and an em-dash in the Oráculo column says "no opinion" — the
state most of a squad is in most of the week.

This also makes the JP-only fallback **self-evident per row**: an empty Oráculo
column down the whole table is the picture of a thin midweek read. The title
marker stays as well, because a reader should not have to infer it from an
absence.

Applies to every table — squad, market and rival views all go through
`build_table_image`.

### The trap this walks into

`image_formatter` already carries a scar from exactly this change. Its comment
records that the clause view's two extra columns "worth 0.36 against the base's
0.86" once shrank the base columns by 30% while the canvas grew 4%, and a
fifteen-player squad came out 1122 px wide and unreadable when zoomed.

The fix then was to widen the figure by what the **extra** columns weigh:

```
fig_w = _BASE_FIG_WIDTH_IN * total_weight / base_weight
```

That formula only compensates for `extra_cols`. Adding two **base** columns
leaves `_BASE_FIG_WIDTH_IN` at 9 inches while the base weight goes 0.86 → 1.03,
so every column loses 17% of its width and the bug comes back by a different
door.

So the change is two edits, not one:

| | weight | canvas |
|---|---|---|
| base today | 0.86 | 9.0 in |
| base + `JP` (0.08) + `Oráculo` (0.09) | 1.03 | **10.8 in** |
| rival view (+0.36) | 1.39 | 14.5 in |

`_BASE_FIG_WIDTH_IN` must rise to ~10.8 with the columns. A test should assert
the rendered pixel width per column does not fall below today's, since that is
the property that actually matters and the one nobody checks by eye.

### The star marks

One `★` per qualifying list, in the Oráculo column beside the number.

**BMP glyphs only.** The same file records that anything above the BMP draws a
dotted-circle placeholder in matplotlib — which is why `_strip_emoji` exists
and the bench markers are `●` and `○` rather than a chair. `★` is U+2605 and
safe; a medal emoji is not.

## The chollos exception: buying to trade, not to field

`chollos` is excluded from the projection because it ranks value, not quality.
The same fact makes it the right list for a **different objective**: buy cheap,
let the price rise, sell.

Evaluated rather than accepted, because it runs against something
`auto_bid` learned the hard way.

### Why it holds up

- **The list is literally about this.** `chollos` ranks `pointsPerMillion`, and
  points per euro is what moves a Biwenger price.
- **There is room.** `MAX_SQUAD_SIZE` is 25 and the squad sits at 14, so a
  speculative buy costs a slot nobody needed.
- **It is cheap.** Base price plus 100–200K on a ~1.1M player.
- **It does not corrupt the tiers.** The SF ladder answers "who improves the
  eleven"; this answers "what will be worth more next week". Different
  questions, so the ladder's boundaries stay untouched.

### Why it needs guarding

**`auto_bid` already carries a scar here.** Its docstring records that a player
who would not make the pitch has his SF clamped to `BENCH_PRICED_SF`, because
"JP scores a benched star highly, and the ladder read that number alone; the
wallet went all-in on players who were not going to play."

This proposal deliberately buys players who will not play. That is the same
shape as the old bug and a different bet: the bug spent *everything* on a
non-player believing he would score; this spends *a little* knowing he will
not. Legitimate — but the guard must be **bypassed explicitly for this path,
with its own hard cap**, never loosened for everyone.

Two conditions follow:

1. **Last in the queue, leftover cash only.** `auto_bid` bids best-SF-first
   until the money runs out. A speculative bid taken ahead of a T2 star is
   strictly worse, so the ladder runs to completion first and chollos spend
   what is left — or nothing.
2. **Its own ceiling**, independent of the tiers: `price + CHOLLO_MARGIN`
   (100–200K), and a cap on how many per matchday so a good chollos week cannot
   quietly convert the whole wallet into bench filler.

### The exit already exists, and it was built for this shape

An earlier draft called this a buy-and-forget machine on the grounds that
nothing sells. That was wrong twice over.

The owner opens the app daily and lists players by hand, so the selling half is
a habit rather than a gap. And `/ofertas` already advises on exactly this
shape — rule 5 of `_recommend`:

```python
# 5. Descarte o fondo de armario con plusvalía → ACEPTAR.
if sf < ab.TIER_T3_MIN and roi_pct is not None and roi_pct > 0:
    return REC_ACCEPT, [f"Fondo de armario (SF {sf}) y plusvalía {roi_pct:+.0f}% vs compra"]
```

A chollo bought to trade is a low-SF player with a positive return over what
was paid. That is the rule's exact antecedent, and `roi_pct` means the system
already knows the purchase price.

So the loop closes without a line of new code: buy automatically, list by hand,
the rival bids, `/ofertas` fires in the next digest recommending **ACEPTAR**
with the percentage, and it is one tap.

The rules also partition correctly by accident of good design. Rule 3 refuses
to sell a *useful* player at a loss; rule 5 sells a *fondo de armario* at a
profit. A chollo is fondo de armario by construction, so it can only ever land
in the second.

Better still, the exit does not even need a rival. Biwenger's own market bids
each day on whatever was listed the day before, and `/ofertas` already tells
the two apart — `👤 rival` against `🤖 Mercado público`. So the trade closes
against the house if nobody else wants him.

No reminder line is needed. The one thing worth checking when this is built is
that a bought-to-trade player really does fall below `TIER_T3_MIN` — if his SF
is high enough to reach rule 3, he stops being a trade and becomes a squad
decision, which is the correct outcome but a different one.

### Getting them bought at all

Two things stand between a chollo and a bid, and neither is the price.

**The ladder skips him outright.** `auto_bid` drops anything under SF 300, and
a chollo is a chollo precisely because he is cheap and low-scoring — the
example in the squad reads SF 103. So the "bonus" this needs is not points on a
projection: it is an **eligibility floor for chollos only**, enough to enter the
bidding set. Nothing else about the ladder changes, and his SF stays what it is
everywhere else.

**Leftover cash may never arrive.** Bidding runs best-SF-first until the money
is gone, so "spend what is left" means that on any busy market day no
speculative bid happens at all — which defeats the point of having the rule.

So a small **reserve** rather than leftovers: hold back roughly the cost of the
day's speculative bids before the ladder starts, so speculation happens on
ordinary days.

With one waiver, because the reserve competes with the one tier that should
never be starved: **when the all-in tier fires (SF ≥ 800), the reserve is
released**. A genuine monster at 800+ is worth more than three lottery tickets,
and that tier already bids the whole wallet by design.

### Bid on every chollo that appears — softly, and that is the safety

The rule is: any chollos player in the day's market gets a bid at base price
plus a small margin. Not a selection among them, all of them.

That sounds reckless and is not, because **a soft bid usually loses**. The
computer market sells to the highest offer, and base + 200K is beaten by anyone
who actually wants the player. So the ones that land are exactly the ones
nobody else bid on — which is the same thing as saying they were available at
close to base price, which is the entire premise of the trade.

The strategy is cheap *because* it is weak. A ladder bid is meant to win; this
one is meant to be there in case nobody else shows up.

Three guards, in descending order of how often they matter:

1. **It usually loses.** Self-limiting by construction.
2. **A cap of ~3 bids a day**, so an unusual market where five chollos surface
   at once cannot quietly commit 6M.
3. **The owner cancels in the app.** Reviewed daily as a habit that already
   exists, so the ceiling is a safety net rather than the only control.

The reserve sizes itself from the day's actual candidates — up to three times
`price + margin` for the chollos really in the market — rather than being a
fixed figure that is wrong on both a quiet and a busy day.

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
