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
- [ ] `fetch_predictions()` → `/biwenger/predicciones`, the broad coverage
      (~366 players)
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
- [ ] No Oráculo opinion → returns `jp_sf` unchanged
- [ ] Clamped both ways, so one bad read cannot invert a ranking
- [ ] Every input stays on the row beside the output

## 4 · The readers, one at a time

- [ ] **Shadow week first**: log `jp_sf` and `custom` side by side, change
      nothing
- [ ] `clausulazo_candidates.sf_of` → `/recomendar` and all three `/emergencia`
      pools
- [ ] `auto_bid`
- [ ] `image_formatter` (display only)
- [ ] `lineup._sf` — **last**, it applies a lineup every morning unattended

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
2. **Calibration.** Shadow-log the thresholds for a week and fit, or start with
   the guessed numbers and adjust by feel?
3. **Read time.** `fixtures[].hasPrediction` now makes a half-filled round
   *detectable* rather than guessed — but the 09:00 digest may still read one.
   Accept it, or read later and closer to kickoff for the lineup specifically?
4. **Unreachable Oráculo.** Fall back to bare JP silently, or say so? (The SLO
   says loudly.)
5. **Which removals actually go** — all three, or only the ones that have never
   produced a line?
6. **Permission.** `robots.txt` allows the pages; the terms of service are a
   separate question, and not one code can settle.
