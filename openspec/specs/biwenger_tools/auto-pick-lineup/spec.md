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

### Requirement: the captain must be someone the provider expects to play

`_pick_captain` SHALL exclude any starter Jornada Perfecta left out of its
projected XI, even one `LINEUP_SUB_STARTS_ABOVE` promoted into the eleven, and
SHALL return `None` rather than hand the armband to one.

Starting such a player is a bet with the bench as insurance. Captaining him
doubles the bet and has none — Biwenger's auto-substitution replaces a starter,
never the captaincy. The flat penalty made this impossible by accident; the
threshold made it reachable for exactly the profile the 3M cap otherwise
selects for, a cheap player with a high projection.

#### Scenario: a promoted substitute is passed over
- **WHEN** an uncalled starter under the cap outranks every called one
- **THEN** the armband goes to the best called starter instead
- *Verifies:* `test_a_promoted_substitute_never_gets_the_armband`

#### Scenario: nobody eligible
- **WHEN** every affordable starter was left out of JP's XI
- **THEN** no captain is picked
- *Verifies:* `test_no_captain_at_all_beats_an_uncalled_one`

### Requirement: a projected substitute strong enough to start, starts

`_sf` SHALL return the full projection for a player Jornada Perfecta leaves out
of its projected XI when that projection exceeds `LINEUP_SUB_STARTS_ABOVE`
(350 by default, tunable by environment variable). Below it he keeps the flat
`_UNCALLED_SF`, ranked under everyone certain to play and still ahead of an
empty slot.

JP **predicts** the eleven, it does not report it. The flat penalty treated the
prediction as fact and threw the projection away: on 2026-08-09 Dani Olmo (659,
the squad's best) and Danjuma (369) both scored 1, so the tie between them
broke arbitrarily — Danjuma started and Olmo was benched behind a 228 starter.

The threshold is a judgement, not a measurement: nothing yet records how often
JP's predicted XI is right. It sits in config so it can move without a deploy.

#### Scenario: a substitute above the threshold
- **WHEN** JP leaves out a player projecting above `LINEUP_SUB_STARTS_ABOVE`
- **THEN** he scores his full projection and competes for the XI
- *Verifies:* `test_a_strong_substitute_keeps_his_projection`,
  `test_the_squad_that_prompted_this_now_starts_its_best_player`

#### Scenario: a substitute below the threshold
- **WHEN** the projection does not clear it
- **THEN** he keeps the flat penalty, below anyone certain to play
- *Verifies:* `test_a_weak_substitute_still_ranks_below_everyone_playing`

#### Scenario: the threshold never resurrects the unavailable
- **WHEN** an injured, sanctioned or fixtureless player projects above it
- **THEN** he still scores zero — the rule lifts substitutes, not absentees
- *Verifies:* `test_an_unavailable_player_is_still_out_however_high_he_projects`

#### Scenario: retuned without a deploy
- **WHEN** `LINEUP_SUB_STARTS_ABOVE` changes
- **THEN** the same player crosses or fails the bar accordingly
- *Verifies:* `test_the_threshold_is_tunable_without_a_deploy`

#### Scenario: every surface tells the same story about a promoted player
- **WHEN** a player above the threshold is started despite JP leaving him out
- **THEN** the squad image does not mark him unavailable
- *Verifies:* `test_a_promoted_substitute_is_not_painted_red`

#### Scenario: the message distinguishes a promotion from a hole-filler
- **WHEN** the XI contains both an uncalled player above the threshold and one
  below it
- **THEN** the promoted player is reported as chosen on projection, and only
  the other carries the "better 0 points than an empty slot" warning
- *Verifies:* `test_format_lineup_message_separates_promoted_from_hole_fillers`

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
