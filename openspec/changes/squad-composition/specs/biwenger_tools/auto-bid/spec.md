# Delta: auto-bid

Drafted for answer 1 (ceiling) of `proposal.md`. The first evidence points
elsewhere; if another answer survives the gate, this delta is rewritten before
any code.

## ADDED Requirements

### Requirement: Between similar projections, the candidate who can win a round ranks first

Candidates SHALL be ranked by their SF adjusted by a capped measure of their
ceiling — how often they have recently had a big round — so that, between two
candidates of similar projection, the one with a real chance of a decisive
score is bid on first. The ceiling SHALL NOT raise the price a tier sets, and
SHALL NOT let a T3/T4 candidate past the rule that he must make the eleven.

The squad the tooling built scored below the league average in 9 of 10
rounds while the projection ranked it second. Its players scored what they
were projected, but rival squads won rounds with one or two explosive players,
and a squad of flat SF 400–500 players has no such round in it.

#### Scenario: a ceiling breaks a near-tie
- **WHEN** two candidates are within the cap of each other in SF and one has
  had big rounds recently **THEN** he ranks first
- *Verifies:* `test_between_two_candidates_of_similar_projection_the_one_with_a_ceiling_ranks_first`

#### Scenario: the ceiling never buys dearer
- **WHEN** a candidate's ceiling moves his rank **THEN** his bid is priced by
  his tier as before
- *Verifies:* `test_the_ceiling_never_raises_the_price_of_a_bid`,
  `test_the_ceiling_adjustment_is_capped`

#### Scenario: the eleven rule still decides
- **WHEN** a T3/T4 candidate with a ceiling would not make the eleven
  **THEN** he is not bid on
- *Verifies:* `test_a_ceiling_does_not_put_a_bench_player_in_the_eleven_rule`
