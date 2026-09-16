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

**Shadow week first**: log `jp_sf` and `custom` side by side, change nothing.

Decisions, in this order — safest first, the unattended one last:

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

- [ ] `provider_watch` — five watchers, twelve months, zero events
- [ ] `log_promotions` — records a bet it cannot grade, ~once a year
- [ ] `deploy-watchdog.yml` — confirm whether it has ever fired first
- [ ] Prune the backlog lines these leave behind

## Open questions — answer before phase 3

1. ~~Which route.~~ **Answered by measurement.** The API gives the lists in
   Biwenger scoring but only 43 unique players — a highlights endpoint, not a
   projection list. `/biwenger/predicciones` gives 366 players and no lists.
   Both are needed, each for its half. Permission decided by the owner and
   recorded in `design.md`.
2. **Calibration.** Two sets of guesses now, not one: the blend thresholds
   (6.0 / 3.0 / 80 / 40 and the ±30/±10/±20) **and**
   `ORACULO_MIN_COVERAGE = 0.60`. Shadow-log both for a week and fit, or start
   with these and adjust by feel?
3. **Read time — now a number, not a feeling.** The next matchday held **67**
   projected players three days out and the current one **252**, so a Tuesday
   read covers a fraction of the squad. `fixtures[].hasPrediction` is no help
   here: it was `true` for all ten fixtures while only 67 players had numbers.
   Accept a thin early read, or read late and close to kickoff for the lineup
   specifically?
4. ~~Unreachable Oráculo.~~ **Answered.** Fall back to JP and say so — a
   marked column header and title in the photos, one line in the Telegram
   surfaces, distinguishing "unavailable" from "not enough data yet".
5. **Which removals actually go** — all three, or only the ones that have never
   produced a line?
6. **Permission.** `robots.txt` allows the pages; the terms of service are a
   separate question, and not one code can settle.
