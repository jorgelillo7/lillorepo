# Tasks

Outcomes, not steps. The test names are a contract: the implementation must
create functions with exactly these names, or the scenario that claims them is
updated in the same PR.

## Behaviour

- [ ] Rebuild mode triggers on "no legal eleven can be filled", not on a count
      of losses, and reads the squad rather than the board
- [ ] The one-player flow is untouched below that threshold
- [ ] The plan targets a legal eleven plus two substitutes
- [ ] Every remaining hole has its cheapest eligible candidate reserved before
      the current hole is committed
- [ ] Positions that block every formation are filled first
- [ ] Candidates are ranked by points per euro inside the affordable band
- [ ] No goalkeeper is ever bought, and no mode targets the goalkeeper line
- [ ] A configured cash floor is kept when the plan completes without it,
      and spent — reported — when it is the difference between fielding an
      eleven and not
- [ ] The preview shows the eleven the plan would field and each signing's cost
- [ ] A plan that cannot reach a legal eleven says so instead of implying one
- [ ] Execution is sequential, re-plans between purchases, substitutes only
      within a hole's position and reserved amount, and reports each outcome

## Defects fixed with it

- [ ] Two goalkeeper losses are reported, never "sin clausulazos recientes"
- [ ] The goalkeeper line is never targeted
- [ ] `force_position` outside 1-4 answers 400 instead of raising `KeyError`

## Tests (exact names)

- [ ] `test_rebuild_mode_triggers_only_when_no_legal_xi_is_possible`
- [ ] `test_a_single_loss_that_still_fields_an_xi_keeps_the_one_player_flow`
- [ ] `test_the_plan_reserves_the_cheapest_candidate_for_every_remaining_hole`
- [ ] `test_a_star_signing_is_refused_when_it_would_starve_the_other_holes`
- [ ] `test_the_plan_fills_the_positions_that_block_every_formation_first`
- [ ] `test_the_plan_ranks_by_points_per_euro_when_money_is_the_constraint`
- [ ] `test_the_plan_never_buys_a_goalkeeper`
- [ ] `test_emergencia_never_targets_the_goalkeeper_line`
- [ ] `test_the_preview_shows_the_eleven_the_plan_would_field`
- [ ] `test_the_plan_states_when_it_cannot_reach_a_legal_xi`
- [ ] `test_the_cash_floor_is_kept_when_the_plan_completes_without_it`
- [ ] `test_completing_the_eleven_wins_over_keeping_the_cash_floor`
- [ ] `test_a_vanished_target_is_replaced_within_its_reserved_amount`
- [ ] `test_nothing_outside_the_confirmed_plan_is_ever_bought`
- [ ] `test_execution_reports_the_outcome_of_every_signing`
- [ ] `test_two_goalkeeper_losses_are_reported_not_silently_dropped`
- [ ] `test_rebuild_mode_takes_precedence_over_the_selector`
- [ ] `test_force_position_outside_the_range_is_a_400_not_a_crash`

## Closing

- [ ] Fold the delta into `openspec/specs/biwenger_tools/clausulazo-emergency/`
      once the code is merged and the named tests pass
- [ ] Delete `openspec/changes/emergency-rebuild-mode/`
- [ ] `python3 scripts/check_specs.py` green
