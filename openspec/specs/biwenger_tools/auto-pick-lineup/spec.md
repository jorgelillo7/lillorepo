# Capability: auto-pick-lineup

Pick the captain for the starting XI and render the lineup message, using
cf-base player values.

- **Source:** `packages/biwenger_tools/api/logic/lineup.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_lineup.py`

---

### Requirement: Captain by highest SF under the 3M price cap

`_pick_captain` SHALL choose the starter with the highest SF whose price is
**strictly below 3M** (`_CAPTAIN_MAX_PRICE = 3_000_000`) — Biwenger returns
HTTP 403 *"Captain over max MV: X > 3000000"* for any captain priced ≥ 3M. The
cap applies to the **cf.biwenger.com base price** (`row["price"]`), NOT the
per-league `owner.price`, which can be much lower — a player who looks cheap in
your league can still be rejected on his cf-base value. Starters with an
unknown (0) price are excluded — never gamble the captaincy on a market value
we can't see. When no starter qualifies it SHALL return `None` (caller PUTs
`captain=0`).

#### Scenario: cap, strictness, unknown price
- **WHEN** several starters qualify **THEN** the highest-SF under 3M wins
- **WHEN** a starter sits exactly at 3M **THEN** it is excluded (strict `<`)
- **WHEN** every starter is over the cap, or all prices are unknown
- **THEN** the result is `None`
- **WHEN** a price-0 starter has the highest SF but known options exist
- **THEN** it does not win
- *Verifies:* `test_pick_captain_picks_highest_sf_under_cap`,
  `test_pick_captain_cap_is_strict`,
  `test_pick_captain_returns_none_when_every_starter_over_cap`,
  `test_pick_captain_returns_none_when_all_prices_unknown`,
  `test_pick_captain_ignores_unknown_price_when_known_options_exist`

### Requirement: Message rendering

`format_lineup_message` SHALL render the lineup, omitting the © captain marker
and showing a no-captain warning when no captain was picked.

#### Scenario: no captain
- **WHEN** captain is `None`
- **THEN** the message omits © and shows the warning
- *Verifies:* `test_format_lineup_message_renders_no_captain_warning`

### Requirement: cf-base pricing

`build_squad_rows` SHALL keep `row["price"]` as the cf.biwenger.com base price,
ignoring any `owner` price block (present or absent) — the same value auto-bid
and offers reason over.

#### Scenario: price source
- **WHEN** a squad entry has, or lacks, an `owner` block
- **THEN** `row["price"]` stays the cf-base price
- *Verifies:* `test_build_squad_rows_keeps_cf_base_price_ignoring_owner`,
  `test_build_squad_rows_keeps_cf_base_price_without_owner`

### Requirement: the formations the optimizer may field

`FORMATIONS` SHALL hold every formation Biwenger's own *Estrategia* picker
offers, and no others. The list is transcribed from the app: it is data the
code cannot derive, and a missing entry is an XI the optimizer will never
propose while nothing else notices. It was two short — `3-2-5` and `5-1-4` —
which also made `draft.composition_ok` reject a squad with a single midfielder
as unable to field a legal eleven.

#### Scenario: the set matches the app
- **WHEN** the fourteen labels Biwenger offers are compared against `FORMATIONS`
- **THEN** the sets are equal
- *Verifies:* `test_formations_match_biwengers_strategy_picker`

#### Scenario: every formation is fieldable
- **WHEN** any formation is read
- **THEN** it totals eleven with the keeper, and needs no more slots in one
  line than the candidate pool holds
- *Verifies:* `test_every_formation_fields_exactly_eleven`

### Requirement: a full bench beats an empty slot

`_pick_reserves` SHALL fill every bench slot the squad can fill, drawing from
the **whole squad** rather than the trimmed starter pool, and SHALL NOT exclude
a player for being injured, suspended, unlisted or without data.

An empty slot scores -4; a player who does not play scores 0. Excluding the
doubtful therefore costs points it cannot win back — and a postponed fixture or
a late recovery turns the excluded player into points.

#### Scenario: doubtful players still sit on the bench
- **WHEN** the squad contains injured or unlisted players and bench slots remain
- **THEN** they are benched rather than left out
- *Verifies:* `test_an_injured_player_fills_a_bench_slot_rather_than_leaving_it_empty`,
  `test_the_bench_is_drawn_from_the_whole_squad_not_the_trimmed_pool`,
  `test_a_projected_substitute_is_available_not_out`

### Requirement: notice what the providers send that this code does not model

`provider_watch.observe` SHALL run before any lineup decision and SHALL log —
never raise, never decide — when Biwenger or Jornada Perfecta send a value
outside what has been observed.

The tracked sets are named for what has been **seen in the wild**, not for what
the code handles. `break` is handled by `_sf` and has never appeared in 533
players; its first sighting must still be reported, because that sighting is
the only thing that can confirm what the branch is for.

Three defects in August 2026 shared one shape — the code holding a rule the
game does not have — and each was found months late by someone happening to
notice. This exists so the next one is dated instead.

#### Scenario: an unmodelled player status
- **WHEN** Jornada Perfecta reports a status outside the six observed
- **THEN** it is logged with the player, and the lineup is unaffected
- *Verifies:* `test_an_unknown_jp_status_is_logged`,
  `test_a_known_jp_status_is_silent`

#### Scenario: the first fixture status that is not `pending`
- **WHEN** a player's `nextMatch.status` is anything else, `break` included
- **THEN** it is logged as never seen before
- *Verifies:* `test_the_first_break_fixture_is_logged`

#### Scenario: the two providers disagree on whether a player can be fielded
- **WHEN** Jornada Perfecta and Biwenger differ on availability
- **THEN** both statuses and Biwenger's note are logged, and Jornada Perfecta
  still decides — the evidence is collected, not acted on
- *Verifies:* `test_providers_disagreeing_on_availability_is_logged`,
  `test_providers_agreeing_is_silent`

#### Scenario: the observer itself fails
- **WHEN** `observe` raises for any reason
- **THEN** it is swallowed and logged; an observer that can break the lineup it
  watches is worse than none
- *Verifies:* `test_the_watcher_never_breaks_a_lineup`
