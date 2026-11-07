# Tasks: value-squad-ceiling

Gated: start only when the evidence in `proposal.md` holds over 8 rounds.

## Evidence (no behaviour change)

- [ ] 8 rounds with `league_projection` and `league_points` in the ledger
- [ ] Projected rank against real rank read for those rounds (`report.py`)
- [ ] Top-two share of points for each round's winner against ours
- [ ] Decision written here: proceed or withdraw

## Behaviour (only if the evidence holds)

- [ ] A pure `ceiling` measure from `fitness`, tested on its own
- [ ] Candidate ranking in auto-bid adjusted by the capped ceiling
- [ ] Tests, with these exact names:
  - [ ] `test_between_two_candidates_of_similar_projection_the_one_with_a_ceiling_ranks_first`
  - [ ] `test_the_ceiling_never_raises_the_price_of_a_bid`
  - [ ] `test_a_ceiling_does_not_put_a_bench_player_in_the_eleven_rule`
  - [ ] `test_the_ceiling_adjustment_is_capped`
- [ ] Delta folded into `openspec/specs/biwenger_tools/auto-bid/spec.md`; this folder deleted
