# Tasks: squad-composition

Gated: nothing in auto-bid or the trader changes until the evidence in
`proposal.md` is read.

## Evidence (no behaviour change)

- [x] `logic/squad_gap.py` and `scripts/projections/squad_gap.py`: each
      manager-round split into base, play, result, clean sheet and the rest,
      plus the top-two share
- [x] Full run, 70 of 70 manager-rounds (in `proposal.md`)
- [ ] Where our wealth fell behind: team value plus cash over the season
- [ ] 8 rounds with `league_projection` and `league_points` in the ledger,
      read with `report.py`
- [ ] Decision written here: which answer survives, or withdraw

## Behaviour (only for the answer that survives)

Answer 1 (ceiling) — the delta in `specs/` as written:

- [ ] A pure `ceiling` measure from `fitness`, tested on its own
- [ ] Candidate ranking in auto-bid adjusted by the capped ceiling
- [ ] Tests, with these exact names:
  - [ ] `test_between_two_candidates_of_similar_projection_the_one_with_a_ceiling_ranks_first`
  - [ ] `test_the_ceiling_never_raises_the_price_of_a_bid`
  - [ ] `test_a_ceiling_does_not_put_a_bench_player_in_the_eleven_rule`
  - [ ] `test_the_ceiling_adjustment_is_capped`

Answer 2 (team strength) or 3 (the rest of the eleven): rewrite the delta in
`specs/` before any code.

- [ ] Delta folded into `openspec/specs/biwenger_tools/auto-bid/spec.md`; this
      folder deleted
