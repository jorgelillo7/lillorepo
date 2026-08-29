# Capability: auto-pick-lineup

Pick the captain for the starting XI and render the lineup message, using
cf-base player values.

- **Source:** `packages/biwenger_tools/api/logic/lineup.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_lineup.py`

---

### Requirement: The search has a ceiling, and abandoning it is not "no lineup"

`_try_fill` is memoised exhaustive backtracking. `_trim_pool_by_position`
saturates the candidate pool around 17 players, so a `MAX_SQUAD_SIZE` (25)
squad and a 30-man one cost the same — but that is a property of the current
trimming, not a guarantee, and the cost of being wrong is not a slow request:
the service runs 512Mi at concurrency 10, and the cache holds one entry per
state (~260 B), so several pathological searches at once is an OOM kill that
takes the container down rather than the request.

- The cache SHALL key on a **bitmask** of remaining players, not a set of
  ids. `MAX_SQUAD_SIZE` is what makes this possible — 25 players is 25 bits —
  and it is the difference between 728 bytes per key and 28. With one key per
  state that choice *is* the memory profile: 321 B per state rather than 1370.
- The cache value SHALL be the chosen player and the score, never the
  sub-assignment; the eleven is rebuilt afterwards by walking the chain.
- The search SHALL count states per formation and abort at
  `_MAX_SEARCH_NODES`, calibrated 3.5x above the worst single formation
  observed across generated maximum-size squads (42,921 states, 13 MB).
- **WHEN** one formation aborts **THEN** the other thirteen SHALL still be
  searched, and a warning logged naming the formation and squad size. The
  eleven returned is worse than the optimum only if the optimum lived in the
  shape that was dropped.
- **WHEN** every formation aborts **THEN** `LineupSearchExhausted` SHALL be
  raised rather than `None` returned. `None` means "this squad cannot field a
  legal eleven", which `/ofertas` turns into a flat RECHAZAR; a search that
  was abandoned is a different fact and must not arrive wearing the same
  clothes.

Per-player reads (`_sf`, `_positions`, `_fallback_rate`, `_back_bias_one`) are
tabled once per `_try_fill` call and the score accumulated incrementally
through the cache. Those tables SHALL NOT be hoisted above the promotion-cap
loop in `_solve`: `_demote_surplus_promotions` flips `_promotion_capped`
between passes and `_sf` reads it, so a table built once per `pick_lineup`
would score demoted players with their pre-demotion projection and pick a
different eleven.

### Requirement: the lineup messages say where the season is

`/preview` and `/alinear` SHALL open with the current round, how many of its
games are played, whether it is still open, the next round's first kickoff and
the moment clauses freeze for it. The state SHALL come from Biwenger's own
round payload, not be inferred from Jornada Perfecta.

**The next round is not the next number.** 2026/27 interleaves postponed
rounds — with Jornada 3 active the next to be played is Jornada 6, and Jornada
4 follows it. The implementation SHALL take Biwenger's `next` and never derive
the next round from the round number or from the order of `season.rounds[]`,
which is not chronological.

Clauses freeze 24 h before that kickoff, so the deadline is what makes the
line actionable: cash has to be positive before it, and until it passes a
player can still be taken.

The read SHALL be best-effort — a failure drops the line and leaves the
message otherwise intact, because losing a lineup because the calendar was
unreachable is the wrong trade.

#### Scenario: the header and its absence
- **WHEN** the round has unplayed games **THEN** it reads as open, with the
  played/total count
- **WHEN** the next round's games carry several kickoffs **THEN** the earliest
  is the one the freeze is measured from
- **WHEN** the payload is missing or partial **THEN** no line is rendered and
  nothing raises
- *Verifies:* `test_an_open_round_is_read_from_its_games_not_assumed`,
  `test_a_finished_round_is_not_open`,
  `test_the_next_round_is_not_the_next_number`,
  `test_the_clause_deadline_is_a_day_before_the_first_kickoff`,
  `test_the_earliest_kickoff_wins_when_the_round_has_several`,
  `test_a_partial_payload_yields_an_empty_context_not_a_crash`,
  `test_no_context_renders_no_line`,
  `test_the_line_names_the_round_the_next_one_and_the_freeze`

### Requirement: the preview compares, it does not just propose

`/preview` SHALL report the difference between the lineup saved on Biwenger
and the optimal one, not the optimal one alone. It SHALL state one of three
outcomes: identical ("nada que aportar"), different (who is in, who is out,
whether the formation or captain changed, and the cost in projected points),
or **not comparable** with the reason — nothing saved, unfilled slots, a
player sold since it was set, or an eleven no formation fits.

A delta of **zero** on a different eleven SHALL be reported rather than
suppressed: it means the swap is free, which is an answer.

The **bench is part of the comparison and not part of the delta**. A saved
lineup whose eleven matches but whose bench differs, or has unfilled slots,
SHALL NOT be reported as identical — it was, and the preview called a lineup
with a hole in its bench optimal. `total_sf` is the starters' score alone
(`_pick_reserves` runs after the search and scores nothing), so the difference
SHALL be stated on its own line saying it gains no points but leaves an absent
starter without cover. Folding an invented number into the delta is the thing
to avoid.

A player who moves **between** the eleven and the bench SHALL be reported
once. The eleven's line already names him; repeating the mirror image below
reads as a contradiction ("Sale: Rioja" from the eleven, "Entra: Rioja" to the
bench) and made the counts disagree — one message claimed two empty slots
while listing three arrivals. The bench lines SHALL carry only bench-only
churn, and the empty-slot count SHALL be the number of bench slots the optimum
fills that the saved lineup does not.

The saved eleven SHALL be scored by putting it back through the solver, and
through `xi_snapshot` rather than `pick_lineup`. Summing `_sf()` over it is
wrong — `_sf` reads `_promotion_capped`, which `_solve` flips between passes,
so a total taken outside the search is not in the same units as
`result["total_sf"]`. And `pick_lineup` writes to `provider_watch`, the trail
that records the promotions actually bet on each morning; a counterfactual
must not bury a real decision.

A failed read SHALL degrade — the optimal eleven still goes out with a line
saying the comparison could not be made — and SHALL NOT synthesise a lineup
to compare against.

`/alinear` SHALL be untouched: an applied lineup and a proposed one must stay
impossible to confuse.

#### Scenario: the three outcomes and their cost
- **WHEN** the saved eleven, formation and captain match **THEN** the preview
  says there is nothing to add
- **WHEN** a starter was swapped **THEN** he is named out, his replacement in,
  and the delta is `optimal − saved`
- **WHEN** the two elevens score the same **THEN** the delta prints as zero
- **WHEN** only the formation, only the captain, or only the bench differs
  **THEN** it is not reported as identical
- **WHEN** the saved lineup has holes, a sold player, or none exists **THEN**
  the preview says why instead of printing a delta
- **WHEN** the read fails **THEN** the preview still renders
- *Verifies:* `test_an_identical_eleven_reports_nothing_to_add`,
  `test_a_swapped_starter_is_reported_in_and_out_with_its_cost`,
  `test_an_equivalent_eleven_reports_a_zero_delta`,
  `test_a_formation_change_alone_is_not_nothing_to_add`,
  `test_a_captain_change_alone_is_not_nothing_to_add`,
  `test_an_incomplete_saved_lineup_is_not_comparable`,
  `test_no_saved_lineup_is_not_comparable`,
  `test_a_sold_player_in_the_saved_lineup_is_not_comparable`,
  `test_a_failed_lineup_read_still_previews`,
  `test_the_comparison_does_not_write_to_provider_watch`,
  `test_applying_a_lineup_is_unchanged_by_the_preview_work`,
  `test_an_empty_bench_slot_is_not_nothing_to_add`,
  `test_the_message_says_the_bench_gains_no_points`,
  `test_a_different_bench_is_reported_in_and_out`,
  `test_a_player_moving_between_eleven_and_bench_is_reported_once`,
  `test_the_hole_count_matches_the_names_listed`

#### Scenario: the ceiling is driven, not just mocked
- **WHEN** the ceiling is lowered far enough **THEN** the real counter fires
  it, and the counter SHALL tick on cache misses only — states and cache
  entries being the same number is what makes the ceiling a memory bound
- *Verifies:* `test_the_counter_actually_fires_the_ceiling`,
  `test_the_counter_measures_cache_misses_only`

#### Scenario: a lineup failure does not cost the whole digest
- **WHEN** the lineup step raises inside `/digests/daily` **THEN** auto-bid
  and offers still run — the chain wraps each step
- *Verifies:* `test_the_digest_survives_an_exhausted_lineup_search`

#### Scenario: a maximum squad, and a pathological one
- **WHEN** a 25-man squad is solved **THEN** it completes, nowhere near the
  ceiling
- **WHEN** one formation exceeds the ceiling **THEN** a lineup still comes back
- **WHEN** all of them do **THEN** `LineupSearchExhausted`, and `/ofertas`
  reads it as an unavailable signal rather than a broken eleven
- *Verifies:* `test_the_ceiling_sits_well_above_a_maximum_squad`,
  `test_a_squad_at_the_league_maximum_still_solves`,
  `test_one_formation_hitting_the_ceiling_does_not_lose_the_lineup`,
  `test_every_formation_hitting_the_ceiling_is_not_reported_as_no_lineup`,
  `test_an_exhausted_search_leaves_offers_on_the_money_rules`

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

### Requirement: the better gamble starts

When a slot can only go to players `_sf` has floored, `pick_lineup` SHALL
prefer the one with the higher underlying projection, and SHALL rank that
above the goal-bonus tiebreaker.

The floor collapses every uncalled player below the threshold to the same
`_UNCALLED_SF`, throwing away that one projects 316 and another 197. With the
scores equal the decision fell to the bias, which favours whoever gains a
bonus by dropping back — so a 197 who happened to be a forward beat a 316 who
did not, and the squad's most expensive player watched from the bench.

The two quantities are orders of magnitude apart: the bias is worth a point or
two of goal bonus, the gap between fallbacks is hundreds of projected points.
Ordering them the other way round is what produced the defect.

A player who **cannot play at all** contributes nothing to this ranking. An
injured 400 is not a better gamble than an uncalled 200 — nobody expects him
on the pitch, and ranking him first would field him.

#### Scenario: two fallbacks for one slot
- **WHEN** a slot can only be filled by players scoring the floor
- **THEN** the higher projection starts, even when the other gains bonus by
  dropping back
- *Verifies:* `test_between_two_fallbacks_the_better_projection_starts`,
  `test_the_projection_gap_outranks_the_bonus_it_could_gain`

#### Scenario: the unavailable are not gambles
- **WHEN** an injured player projects higher than an uncalled one
- **THEN** he still ranks last
- *Verifies:* `test_an_injured_player_is_never_the_better_gamble`

### Requirement: ties are broken by what playing out of position is worth

When two elevens project the same total SF, `_back_bias` SHALL decide between
them with the **difference in Biwenger's goal bonus** for each player moved
from his natural position — `GOAL_BONUS = {POR 10, DEF 7, MED 5, DEL 4}` — and
not merely with the direction of the move.

JP's SF is one number per player and does not model the slot bonus, so this is
the only thing left to compare on. Direction alone made a gain and a loss
cancel: a forward covering midfield gains 1, and the defender pushed out to
free that slot loses 2. Two candidate elevens of a real squad therefore tied at
+1, and the winner fell through to the order of `FORMATIONS` — a list
transcribed from the app, in no meaningful order.

Deltas rather than the slots' own bonuses: summing those would score the
*formation* instead of the placement, and would always prefer five defenders
even with nobody out of position.

#### Scenario: what a move is worth
- **WHEN** a forward fills a midfield slot **THEN** it is worth +1
- **WHEN** a defender is pushed into midfield **THEN** it costs -2
- **WHEN** a player fills his own position **THEN** it is worth nothing
- *Verifies:* `test_playing_a_forward_in_midfield_is_worth_one_bonus_point`,
  `test_pushing_a_defender_into_midfield_costs_two`,
  `test_a_player_in_his_own_position_is_worth_nothing_either_way`

#### Scenario: the elevens that used to tie
- **WHEN** one eleven moves only a forward back and the other also pushes a
  defender forward to make room
- **THEN** the first is strictly better, and no list order is consulted
- *Verifies:* `test_the_two_candidate_elevens_no_longer_tie`

### Requirement: a full bench beats an empty slot

`_pick_reserves` SHALL fill every bench slot the squad can fill, drawing from
the **whole squad** rather than the trimmed starter pool, and SHALL NOT exclude
a player for being injured, suspended, unlisted or without data.

An empty slot scores -4; a player who does not play scores 0. Excluding the
doubtful therefore costs points it cannot win back — and a postponed fixture or
a late recovery turns the excluded player into points.

The slot SHALL go to the substitute most likely to be worth something:
highest `_sf`, then the projection behind a floored score, then how many
positions he covers.

Sorting on `_sf` alone left the bench deciding ties by squad order. On a real
squad a doubtful forward projecting 63 took the place of a fit one projecting
197 — both floored to `_UNCALLED_SF`, and the wrong one was first in the list.
Versatility comes last because Biwenger's auto-substitution replaces a starter
with a bench player who covers that position, so a DEL/MED reaches two lines
where a MED-only reaches one.

#### Scenario: two floored substitutes for one slot
- **WHEN** a bench slot can only go to players scoring the floor
- **THEN** the higher projection takes it, and a doubtful one does not
- **WHEN** they also project the same **THEN** the one covering more
  positions takes it
- **WHEN** a substitute is expected to play at all **THEN** he outranks both
- *Verifies:* `test_the_bench_prefers_the_substitute_most_likely_to_be_worth_something`,
  `test_a_versatile_substitute_covers_more_than_a_narrow_one`,
  `test_the_bench_never_outranks_a_player_who_is_actually_playing`

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

### Requirement: one promoted substitute per line, never two

`pick_lineup` SHALL promote at most **one** player per position line, keeping
the highest projection in each and returning every other candidate in that line
to the flat `_UNCALLED_SF`.

Biwenger's auto-substitution replaces at most one absent starter per position.
A second promoted substitute in the same line therefore starts with no
insurance: if both bets are wrong, only one is covered. Nothing bounded this —
three uncalled midfielders above the threshold and three certain ones below
could all start behind a single midfield bench slot.

The cap is not a filter. A capped player keeps `_UNCALLED_SF` (1), still beats
an empty slot, and still starts when his line has nobody certain — where he is
reported under the existing "sin estar convocados" warning, which is the truth:
he is there because nothing better exists.

The line that counts is the one a player is **assigned** to, not his primary —
a promoted defender who also covers midfield spends a midfield bench slot. That
is only knowable once the XI exists, so the search runs to a fixpoint: solve,
demote any surplus promotion, solve again. Each pass demotes at least one player
and never restores one, so it terminates in at most one pass per promotion.

Capping on primary position alone would miss exactly this case, and capping a
multi-position player against every line he could cover would demote players who
would have been assigned elsewhere.

#### Scenario: two candidates in one line
- **WHEN** two uncalled players in the same line both clear the threshold
- **THEN** only the higher projection keeps it; the other drops below anyone
  certain to play
- *Verifies:* `test_only_the_top_promotion_in_a_line_keeps_his_projection`

#### Scenario: the cap is per line, not per XI
- **WHEN** two lines each hold a promoted candidate
- **THEN** both are promoted — the exposure is per position, so the limit is too
- *Verifies:* `test_promotions_in_different_lines_are_both_kept`

#### Scenario: a capped player with no alternative still plays
- **WHEN** a capped player's line has no certain starter to fall back on
- **THEN** he starts anyway, ahead of the empty slot and its -4
- *Verifies:* `test_a_capped_player_still_starts_when_his_line_has_no_certain_alternative`

#### Scenario: a multi-position promotion cannot smuggle in a second bet
- **WHEN** a promoted player whose own line is full of stronger certain
  starters is assigned to a second line that already holds a promotion
- **THEN** one of the two is demoted — the limit follows the assignment, not
  the primary position
- *Verifies:* `test_the_cap_holds_for_the_line_a_player_is_actually_assigned_to`

#### Scenario: the mark never outlives the call that set it
- **WHEN** `pick_lineup` runs twice on the same row dicts
- **THEN** the second run decides from scratch — a mark from the first can
  neither survive nor accumulate
- *Verifies:* `test_the_promotion_mark_is_not_stale_across_calls`

### Requirement: every promotion that starts is recorded with what it displaced

`provider_watch.log_promotions` SHALL log one line per promoted player who
**reaches the starting XI**, carrying his projection, the threshold in force,
his line, and the highest-SF certain squad member he kept out of it.

`LINEUP_SUB_STARTS_ABOVE` decides every morning whether the projection outranks
the provider's own predicted XI, and the 350 default is a judgement nobody can
improve without knowing how often that bet pays. Neither provider exposes
whether a player featured: Jornada Perfecta's payload is forward-looking, and
the Biwenger competition data these rows are built from carries no per-round
points. So this records the bet rather than grading it — the verdict comes from
reading a round's real points against the lines logged that morning.

The displaced player is the point. *"659 started instead of 228"* can be graded
later; *"659 started"* cannot.

A promotion that loses its place to a better assignment is not logged: no bet
was placed. Like everything in `provider_watch`, this decides nothing and
SHALL NOT raise into the lineup path.

#### Scenario: a promotion that starts
- **WHEN** a promoted player makes the XI over a certain starter
- **THEN** both names and both scores are logged, with the threshold in force
- *Verifies:* `test_a_promotion_that_starts_is_logged_with_its_displaced_starter`

#### Scenario: nobody was displaced
- **WHEN** the line held no certain alternative
- **THEN** the line is still logged, saying so explicitly rather than omitting it
- *Verifies:* `test_a_promotion_with_no_certain_alternative_is_logged_with_displaced_none`

#### Scenario: a promotion that never started
- **WHEN** a promoted candidate does not make the XI
- **THEN** nothing is logged for him
- *Verifies:* `test_a_promotion_that_does_not_start_is_not_logged`

#### Scenario: the recorder cannot break the lineup
- **WHEN** `log_promotions` is handed malformed input
- **THEN** it is swallowed and logged
- *Verifies:* `test_log_promotions_never_raises`

### Requirement: notice what the providers send that this code does not model

`provider_watch.observe` SHALL run before any lineup decision and SHALL log —
never raise, never decide — when Biwenger or Jornada Perfecta send a value
outside what has been observed.

A player Jornada Perfecta does not carry at all SHALL be named too. The
module skipped that row entirely, which is the one case it was best placed to
catch: such a player scores zero and is fielded unseen, and when it took the
league value ranking down nothing in the logs could name him — the state had
healed by the time anyone looked.

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

#### Scenario: a player the provider does not carry at all
- **WHEN** Jornada Perfecta has no entry for a squad player
- **THEN** he is named in the log — the sets above watch for values a
  provider sends, and this is the provider not sending the player
- *Verifies:* `test_a_player_jornada_perfecta_does_not_carry_is_logged`,
  `test_a_matched_player_is_not_reported_as_missing`

#### Scenario: the observer itself fails
- **WHEN** `observe` raises for any reason
- **THEN** it is swallowed and logged; an observer that can break the lineup it
  watches is worse than none
- *Verifies:* `test_the_watcher_never_breaks_a_lineup`
