# Tasks

Outcomes, not steps. The test names are a contract: the implementation must
create functions with exactly these names, or the scenario that claims them is
updated in the same PR.

## Behaviour

- [x] Rebuild mode triggers on "no legal eleven can be filled", not on a count
      of losses, and reads the squad rather than the board
- [x] The one-player flow is untouched below that threshold
- [x] The plan targets a legal eleven plus two substitutes
- [x] Every remaining hole has its cheapest eligible candidate reserved before
      the current hole is committed
- [x] Positions that block every formation are filled first
- [x] Candidates are ranked by points per euro inside the affordable band
- [x] No goalkeeper is ever bought, and no mode targets the goalkeeper line
- [x] A configured cash floor is kept when the plan completes without it,
      and spent — reported — when it is the difference between fielding an
      eleven and not
- [x] The preview shows the eleven the plan would field and each signing's cost
- [x] A plan that cannot reach a legal eleven says so instead of implying one
- [x] Execution is sequential, re-plans between purchases, substitutes only
      within a hole's position and at or under the price the plan approved for
      it, and reports each outcome
- [x] A plan with no signings is never stored, and offers no confirmation
- [x] The eleven's holes and the bench's signings are tracked separately: a
      bench signing is bought on its own terms (still available, at or under
      its approved price) or reported unavailable, never substituted, and
      eleven signings are processed before bench ones regardless of storage
      order
- [x] A downstream failure after a purchase — a Telegram report, or the
      closing cash/eleven check — is logged and downgraded to a warning
      rather than losing the record that money already moved

## Defects fixed with it

- [x] Two goalkeeper losses are reported, never "sin clausulazos recientes"
- [x] The goalkeeper line is never targeted
- [x] `force_position` outside 1-4 answers 400 instead of raising `KeyError`
- [x] A bench signing's line was checked against the eleven's hole count and
      always found empty, reporting it skipped even when the player was
      still there to buy

## Tests (exact names)

- [x] `test_rebuild_mode_triggers_only_when_no_legal_xi_is_possible`
- [x] `test_a_single_loss_that_still_fields_an_xi_keeps_the_one_player_flow`
- [x] `test_the_plan_reserves_the_cheapest_candidate_for_every_remaining_hole`
- [x] `test_a_star_signing_is_refused_when_it_would_starve_the_other_holes`
- [x] `test_the_plan_fills_the_positions_that_block_every_formation_first`
- [x] `test_the_plan_ranks_by_points_per_euro_when_money_is_the_constraint`
- [x] `test_the_plan_never_buys_a_goalkeeper`
- [x] `test_emergencia_never_targets_the_goalkeeper_line`
- [x] `test_the_preview_shows_the_eleven_the_plan_would_field`
- [x] `test_the_plan_states_when_it_cannot_reach_a_legal_xi`
- [x] `test_the_cash_floor_is_kept_when_the_plan_completes_without_it`
- [x] `test_completing_the_eleven_wins_over_keeping_the_cash_floor`
- [x] `test_a_vanished_target_is_replaced_within_its_clause_at_plan`
- [x] `test_nothing_outside_the_confirmed_plan_is_ever_bought`
- [x] `test_execution_reports_the_outcome_of_every_signing`
- [x] `test_two_goalkeeper_losses_are_reported_not_silently_dropped`
- [x] `test_rebuild_mode_takes_precedence_over_the_selector`
- [x] `test_force_position_outside_the_range_is_a_400_not_a_crash`
- [x] `test_preview_rebuild_does_not_store_a_plan_with_no_signings`
- [x] `test_a_bench_signing_is_bought_on_its_own_terms_not_against_a_hole`
- [x] `test_a_bench_signing_is_reported_unavailable_not_swapped_for_a_decoy`
- [x] `test_bench_and_eleven_signings_are_told_apart_by_marker_not_by_list_order`
- [x] `test_a_telegram_failure_after_a_purchase_does_not_abort_the_run`
- [x] `test_every_purchase_is_logged_even_if_telegram_never_hears_about_it`
- [x] `test_a_lineup_search_exhaustion_in_the_final_check_does_not_crash_execution`
- [x] `test_a_cash_read_failure_in_the_final_check_does_not_crash_execution`

## Closing

- [ ] Fold the delta into `openspec/specs/biwenger_tools/clausulazo-emergency/`
      once the code is merged and the named tests pass
- [ ] Delete `openspec/changes/emergency-rebuild-mode/`
- [ ] `python3 scripts/check_specs.py` green
