# Tasks

Five phases, one PR each, merged before the next starts. Test-first throughout
(`logic/` and `core/` — the test is written and observed failing first).

## 1 · The reader — `core/sdk/oraculo.py`

Two sources, because neither covers the other's half (see design):

- [ ] `fetch_picks(sistema="biwenger-sofascore")` → the API. Returns the eight
      lists, `matchday`, `generatedAt`, `modelTag`, `fixtures`
- [ ] **Assert the echoed `sistema` matches what was asked**, and raise if not.
      This is the single check that stops the projections silently halving the
      day the site changes a default
- [ ] `fetch_predictions()` → `/biwenger/predicciones`. **Filter by
      `fixtureDate`** — and note the two sources disagree on the same player
      (Mbappé 11.46 on the API vs 7.39 on the page, six hours apart), so the
      number must come from **one** of them, never a mix: the 366 rows span two matchdays, and the upcoming one
      held 67 projected players three days out against the current one's 252
- [ ] `_flight(html)` / `_objects(payload, key)` for the page route — the only
      fragile parts, isolated so a layout change breaks one test loudly
- [ ] `OraculoError`, raised — never a silent empty list
- [ ] Honest `User-Agent` with a contact address. **Never browser headers.**
- [ ] One call per run per source, cached for an hour (`modelTag` /
      `generatedAt` make the cache key honest)
- [ ] **Fixtures are saved payloads** under `core/tests/fixtures/`; no test
      touches the network

## 2 · The third join — `logic/rows.py`

- [ ] Match on `player_matching.py`, like JP
- [ ] Row gains `oraculo_points`, `oraculo_chance`, `oraculo_lists`,
      `oraculo_matched` — all optional, all raw
- [ ] A test that an unmatched player is `matched=False` and **not** zero

## 3 · The blend — `logic/custom_prediction.py`

- [ ] Pure function, no I/O
- [ ] **No absolute thresholds.** `k = median(jp_sf / oraculo_points)` over the
      covered rows of that read, then `custom = jp*(1-W) + oraculo*k*W`. The
      6.0/3.0 guesses came from the LaLiga Fantasy scale and fail on
      Biwenger's: on a real squad only Mbappé cleared 6.0 and four of thirteen
      fell below 3.0
- [ ] `chance` is a **guard, not a bonus** — `expectedPoints == predicted ×
      chance` on the API and the page column is labelled "Esperado", so the
      number is probably already post-chance and a bonus would double-count.
      Below a floor (~25%) damp the contribution; above it, do nothing
- [ ] The regression cases from the calibration squad: Aubameyang −15%,
      Redondo +55%, Hancko unchanged
- [ ] No Oráculo opinion → returns `jp_sf` **unchanged**
- [ ] **Clamped at `ORACULO_MAX_MOVE = 0.25` both ways.** A weighted average
      drags the extremes toward the population median: on the real squad a
      backup keeper at JP 12 came out 37 (+212%) purely for existing in the
      feed. The clamp only bites on outliers — every player in the body of the
      distribution is bit-identical with and without it
- [ ] Every input stays on the row beside the output

### The three fallbacks, each with its own test

- [ ] **Per player** — not carried by Oráculo → `custom == jp_sf`, unmarked.
      The normal state for most of a squad most of the week
- [ ] **Per read** — `covered < ORACULO_MIN_COVERAGE` (0.60 to start) → blend
      off for the **whole** read, marked. A partial blend is worse than none:
      three boosted players jump the queue only because Oráculo looked at
      their fixture first, and nobody can see why
- [ ] **Per source** — timeout, HTTP error, unparseable payload, **or an
      echoed `sistema` that is not the one asked for** → blend off, logged
      loudly, marked. A wrong `sistema` is a failure, not a warning: believing
      LaLiga Fantasy numbers are Biwenger's is worse than having no second
      opinion
- [ ] A test that the digest still sends when Oráculo is down

## 4 · The readers — seven, not four

The first draft of this plan listed four. A full sweep found seven, and
`offers.py` spends money.

**No shadow week** — decided. The ±50% clamp and the tests are the safety net,
and the order below is the rest of it: display first, then decisions, with the
unattended one last.

Display first, where a wrong number is visible and costs nothing:

- [ ] `image_formatter` — the `Proyección` column, the new `Oráculo` column and
      the marker
- [ ] `league_compare` — the league-wide ranking
- [ ] `actions.py` / `player_formatting` — row rendering

Then the decisions, safest first:

- [ ] `offers.py` — reads `get_predict_rate(..., 2)` directly in two places to
      value an incoming offer. Missed in the first draft because it does not
      go through `sf_of`, and the one place a wrong number costs money today
      rather than points on Sunday
- [ ] `clausulazo_candidates.sf_of` → `/recomendar` + all three `/emergencia`
      pools
- [ ] `auto_bid`
- [ ] `lineup._sf` — **last**. It applies a lineup every morning with nobody
      watching

Display:

- [ ] `image_formatter` — the `Proyección` column, **and the marker**
- [ ] `league_compare` — the league-wide ranking
- [ ] `actions.py` / `player_formatting` — row rendering

### The new column — the inputs beside the output

- [ ] A `Oráculo` column in the photos showing `points · chance` (e.g.
      `7.4 · 80%`), beside the blended `Proyección`. The formula stays arguable
      at a glance without leaving Telegram
- [ ] Empty for a player Oráculo does not carry — an empty cell reads as "no
      opinion", which is what it is
- [ ] `_BASE_COLUMNS` widths need rebalancing; the table is already 7 columns

### The marker

- [ ] Photos: column header becomes `Proyección (JP)` and the title takes a
      suffix when the blend is off. **Text first, colour second** —
      `image_formatter`'s own rule is that shape carries meaning and hue
      reinforces, so a red tint alone is not enough
- [ ] Telegram text (`/recomendar`, `/emergencia`, `/ofertas`): one line,
      distinguishing *"Oráculo no disponible"* (level 3, broken) from
      *"sin datos suficientes"* (level 2, just early in the week) — they call
      for different reactions
- [ ] A test that the marker appears in both cases and **is absent** when the
      blend ran

## 4b · The list bonus, inside the one number

Everything lands in the projection field: JP base, the Oráculo blend, and a
bonus for each shortlist a player appears on. One column to read.

An earlier draft kept the lists out of the score because they cover 38 players
of ~500. That conflated two different kinds of gap. The **points** coverage is
arbitrary — it depends which fixtures the model processed first — which is why
a partial blend distorts. The **lists** are a deliberate top-N: being absent is
the normal state of 92% of players, not missing data.

- [ ] `LIST_BONUS` (0.03 to start) per qualifying list, capped at 3, applied
      after the blend so the bonus stays secondary to it
- [ ] Qualifying: `goleadores`, `asistentes`, `porteros`, `defensas`,
      `centrocampistas`, `delanteros`
- [ ] **`chollos` excluded.** It ranks *value*: its players average 1.1M and
      4.10 points against 7.0M and 5.10 for every other list, and only 2 of 10
      also appear on a best-per-position list. A points bonus for it would
      promote cheap players in the eleven, where price is irrelevant — the
      mistake the draft optimiser already makes with cameo totals. It feeds
      **bid priority** instead, where price is the whole point
- [ ] **`capitanes` excluded** as derived — every 3-and-4-list player is on it,
      so it double-counts the others. Revisit if that stops being true
- [ ] A test that stacking works and that the cap holds: on real data 24
      players were on one list, 8 on two, 4 on three, 2 on four
- [ ] Env-tunable, like every other guess here

### Showing it in the photos — three columns

- [ ] `JP` and `Oráculo` join `Proyección` in `_BASE_COLUMNS`. Raw inputs beside
      the output, so the formula is arguable without leaving Telegram
- [ ] Every table gets them — squad, market and rival views all go through
      `build_table_image`
- [ ] `—` in the Oráculo column means no opinion, which makes a thin midweek
      read **self-evident per row** rather than only in the title
- [ ] One `★` per qualifying list beside the Oráculo number. **BMP glyphs
      only**: `image_formatter` records that anything above the BMP draws a
      dotted-circle placeholder in matplotlib, which is why `_strip_emoji`
      exists and the bench markers are `●`/`○`. `★` is U+2605 and safe
- [ ] **Raise `_BASE_FIG_WIDTH_IN` from 9 to ~10.8** in the same commit. The
      existing `fig_w` formula only compensates for `extra_cols`; two new *base*
      columns take the weight from 0.86 to 1.03 and would shrink every column
      by 17% on an unchanged canvas — which is the exact bug the file's own
      comment records from the clause view (1122 px, unreadable zoomed in)
- [ ] A test on **pixels per column**, not on the weights. The property that
      matters is that a column is no narrower than today, and it is the one
      nobody checks by eye

### The goal and assist probabilities

Correlated against `predictedPoints` over the 32 players carrying both:
`goalProbability` r = +0.50, `assistProbability` r = +0.11; by position +0.56 /
+0.18 / +0.10 for forwards, midfielders, defenders. The points absorb about a
quarter of the goal signal and leave three quarters — not redundant, and for
defenders nearly independent.

- [ ] Feed them to `_pick_captain`, which already reasons about tail versus
      mean. Narrow by construction: Biwenger caps the captain at 3M and only 14
      of the 38 fall under it
- [ ] A test on the real shape: Pedro Díaz 5.85 points at 3.9% goal against
      Marcos Fernández 3.98 at 21.1% — the captain should prefer the second and
      the eleven should still prefer the first

## 4c · The chollos trade (an evaluated exception)

Buy cheap from the `chollos` list, let the price rise, sell. Not for the
eleven — these players average 1.1M and 4.10 points and will not be fielded.

- [ ] Bid `price + CHOLLO_MARGIN` (100–200K) on **every** chollos player in the
      day's market, not a selection among them
- [ ] Rely on the bid being weak. The market sells to the highest offer, so
      base + 200K loses to anyone who actually wants him — the ones that land
      are the ones nobody else bid on, which is the premise of the trade. The
      cap and the manual cancel are the second and third guards, not the first
- [ ] Size the reserve from the day's real candidates (up to 3 × `price +
      margin` for the chollos actually in the market), not a fixed figure that
      is wrong on both a quiet and a busy day
- [ ] **An eligibility floor for chollos only.** The ladder skips SF < 300 and
      a chollo is low-SF by definition (the one in the squad reads 103), so
      without this no speculative bid is ever placed. It lifts him into the
      bidding set and changes his SF nowhere else
- [ ] **A reserve, not leftovers.** Best-SF-first spending means "what is left"
      is often nothing, which would make the rule fire only on quiet days. Hold
      back roughly the day's speculative budget before the ladder starts
- [ ] **Release the reserve when the all-in tier fires** (SF ≥ 800). That tier
      bids the whole wallet by design and a genuine monster beats three lottery
      tickets
- [ ] **Its own cap**, and ~3 bids a day, so a good chollos week cannot convert
      the wallet into bench filler. The owner reviews the day's bids in the app
      and cancels what does not convince, so the ceiling is a safety net rather
      than the only control
- [ ] **Bypass `BENCH_PRICED_SF` explicitly for this path only.** That clamp
      exists because the ladder once went all-in on a benched star; this is the
      same shape and a different bet — a little, knowingly, rather than
      everything, mistakenly. Loosening the clamp for everyone would reopen the
      original bug
- [ ] **No exit code needed — `/ofertas` rule 5 already is it.** `sf <
      TIER_T3_MIN and roi_pct > 0 → ACEPTAR, "fondo de armario con plusvalía"`
      is the exact shape of a chollo bought to trade, and `roi_pct` means the
      purchase price is already known. Owner lists by hand daily, rival bids,
      the digest recommends accepting with the percentage, one tap
- [ ] Verify a bought-to-trade player really lands under `TIER_T3_MIN`. Above
      it he reaches rule 3 — "useful player, that loss is excessive" — which is
      correct behaviour but means he stopped being a trade and became a squad
      decision
- [ ] A test that a chollos bid never consumes cash the ladder wanted

## 5 · The removals

- [ ] `provider_watch` — five watchers, twelve months, zero events. A real
      second source makes "the providers disagree" the signal itself rather
      than an anomaly to date. Takes #443's market widening with it, which is
      the cost of the decision
- [ ] `log_promotions` — records a bet it cannot grade, ~once a year, and we
      decided against building the pipeline that would grade it
- [ ] ~~`deploy-watchdog.yml`~~ — **keep. The check said so.** 40 runs since
      2026-08-08, all "success", and it has **never dispatched**: the three
      `workflow_dispatch` deploys on record are at 19:35, 21:02 and 21:48 UTC
      while the watchdog runs at 07:47, so they were manual. But the failure it
      guards is demonstrably alive — GitHub swallowed two push events on this
      repo on 2026-09-16 alone. Both were on a feature branch, where the cost
      is a missing CI run; on master the cost is a missing deploy, which is
      exactly what this catches. Never having fired is what a working smoke
      alarm looks like
- [ ] Prune the backlog lines these leave behind

## Open questions — answer before phase 3

1. ~~Which route.~~ **Answered by measurement.** The API gives the lists in
   Biwenger scoring but only 43 unique players — a highlights endpoint, not a
   projection list. `/biwenger/predicciones` gives 366 players and no lists.
   Both are needed, each for its half. Permission decided by the owner and
   recorded in `design.md`.
2. ~~Calibration.~~ **Answered against the real squad**, with the effect of each
   option on the table before choosing:

   | | value |
   |---|---|
   | `ORACULO_W` | 0.30 |
   | `ORACULO_MIN_COVERAGE` | 0.60 |
   | `ORACULO_LIST_BONUS` | 0.03, capped at 3 lists |
   | `CHOLLO_MARGIN` | 150K flat |
   | `ORACULO_MAX_MOVE` | 0.25 — found by running on the real squad |
   | chollo synthetic SF | 300 — the bare minimum to be seen |

   All env-tunable. The three columns keep it cheap to revisit: a week of
   photos shows whether the Oráculo column is usually full or usually dashes.
3. ~~Read time.~~ **Answered: one read per execution, cached an hour**, the
   same shape `jp.py` already uses. The model retrains hourly, so reading more
   often buys nothing. A midweek read will simply fall under the coverage
   threshold and mark itself as JP-only, which is the correct outcome rather
   than a compromise.
4. ~~Unreachable Oráculo.~~ **Answered, and the three columns improved it.**
   Fall back to JP and say so. With a raw `Oráculo` column, a failed or thin
   read is visible **per row** as a column of em-dashes rather than inferred
   from a header. The title marker and the Telegram line stay, still separating
   "unavailable" from "not enough data yet".

   Worth recording that this weakens — but does not remove — the case for the
   all-or-nothing coverage rule. The original argument was that a partial blend
   distorts the ranking *invisibly*; with the column it is no longer invisible.
   It still distorts, though, and the eleven is applied unattended at 09:00
   before anyone looks at a photo. So visibility helps the human afterwards,
   not the decision that already happened.
5. ~~Which removals.~~ **Answered: `provider_watch` and `log_promotions` go,
   the deploy watchdog stays** — the check it was conditional on produced a
   reason to keep it.
6. **Permission.** `robots.txt` allows the pages; the terms of service are a
   separate question, and not one code can settle.
