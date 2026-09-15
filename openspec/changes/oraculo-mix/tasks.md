# Tasks

Five phases, one PR each, merged before the next starts. Test-first throughout
(`logic/` and `core/` — the test is written and observed failing first).

## 1 · The reader — `core/sdk/oraculo.py`

- [ ] `_flight(html)` and `_objects(payload, key)`, the only fragile parts
- [ ] `fetch_biwenger_predictions()` → `/biwenger/predicciones`
- [ ] `fetch_oraculo_lists()` → the named arrays
- [ ] `next_matchday(rows)` → filter on `fixtureDate`
- [ ] `OraculoError`, raised — never a silent empty list
- [ ] **Fixtures are saved HTML** under `core/tests/fixtures/`; no test touches
      the network
- [ ] A test asserting the payload really is Biwenger-scored, so the day the
      site changes its default the suite says so rather than the projections
      quietly halving

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

1. **The list flags come from the wrong system.** They exist only on
   LaLiga-Fantasy-scored pages; `/biwenger/predicciones` has none. A "chollo"
   under LaLiga scoring is not necessarily one under Biwenger. Keep them as a
   weak signal, or drop the list half and use only points + chance?
2. **Calibration.** Shadow-log the thresholds for a week and fit, or start with
   the guessed numbers and adjust by feel?
3. **Read time.** The 09:00 digest may read a half-empty round. Accept it, or
   read later and closer to kickoff for the lineup specifically?
4. **Unreachable Oráculo.** Fall back to bare JP silently, or say so? (The SLO
   says loudly.)
5. **Which removals actually go** — all three, or only the ones that have never
   produced a line?
6. **Permission.** `robots.txt` allows the pages; the terms of service are a
   separate question, and not one code can settle.
