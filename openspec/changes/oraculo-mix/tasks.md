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
      `fixtureDate`**: the 366 rows span two matchdays, and the upcoming one
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
- [ ] The worked case: JP 500 + benched + Oráculo > 6.00 → ≈ 1.4×
- [ ] No Oráculo opinion → returns `jp_sf` **unchanged**
- [ ] Clamped both ways, so one bad read cannot invert a ranking
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
2. **Calibration — the only one genuinely still open.** Two sets of guesses:
   the blend thresholds (6.0 / 3.0 / 80 / 40 and the ±30/±10/±20) and
   `ORACULO_MIN_COVERAGE = 0.60`. With no shadow week they go live as written,
   so they must be **env-tunable without a deploy**, the way
   `LINEUP_SUB_STARTS_ABOVE` already is — and that config drift has bitten once
   already, so the default in the code must be the value that runs.
3. ~~Read time.~~ **Answered: one read per execution, cached an hour**, the
   same shape `jp.py` already uses. The model retrains hourly, so reading more
   often buys nothing. A midweek read will simply fall under the coverage
   threshold and mark itself as JP-only, which is the correct outcome rather
   than a compromise.
4. ~~Unreachable Oráculo.~~ **Answered.** Fall back to JP and say so — a
   marked column header and title in the photos, one line in the Telegram
   surfaces, distinguishing "unavailable" from "not enough data yet".
5. ~~Which removals.~~ **Answered: `provider_watch` and `log_promotions` go,
   the deploy watchdog stays** — the check it was conditional on produced a
   reason to keep it.
6. **Permission.** `robots.txt` allows the pages; the terms of service are a
   separate question, and not one code can settle.
