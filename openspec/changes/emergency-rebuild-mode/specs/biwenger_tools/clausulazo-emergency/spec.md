## ADDED Requirements

### Requirement: Rebuild mode replaces the single pick when the eleven is gone

`/emergencia` SHALL check whether the remaining squad can fill any legal
formation. When it cannot, the flow SHALL propose a **plan** — the set of
signings that restores a legal eleven plus two substitutes — instead of a single
target. When it can, the existing one-player flow SHALL run unchanged.

The trigger reads the squad, not the board: a count of losses is a proxy that
gets both ends wrong, and a squad broken by sales or by losses older than the
detection window needs the rebuild just as much as one raided this morning.

#### Scenario: broken squad, and a loss it can absorb
- **WHEN** no formation can be filled from the remaining players **THEN** a plan
  is proposed
- **WHEN** the squad still fields an eleven **THEN** the single-target flow runs
  as before
- *Verifies:* `test_rebuild_mode_triggers_only_when_no_legal_xi_is_possible`,
  `test_a_single_loss_that_still_fields_an_xi_keeps_the_one_player_flow`

### Requirement: Every remaining hole is paid for before the first one is

Before a signing is added to the plan, the cheapest eligible candidate for each
**remaining** hole SHALL be reserved, and only the balance SHALL be spendable on
that signing. A candidate that would leave any remaining hole unfillable SHALL
NOT be treated as affordable, whatever the account balance shows.

This is the failure the change exists for. Ranking by predicted points with
price as a mere cut-off is right for one hole and ruinous for seven: the first
purchase takes the best player the whole budget can buy and the other six become
unaffordable.

#### Scenario: a star that starves the plan
- **WHEN** the highest-scoring affordable rival would leave a later hole
  unfillable **THEN** it is excluded from the plan
- **WHEN** the plan is built **THEN** every remaining hole has its cheapest
  eligible candidate reserved
- *Verifies:* `test_the_plan_reserves_the_cheapest_candidate_for_every_remaining_hole`,
  `test_a_star_signing_is_refused_when_it_would_starve_the_other_holes`

### Requirement: Blocking holes first, then value for money

The plan SHALL fill the positions that block every available formation before
any other, and SHALL rank candidates within the affordable band by predicted
points **per euro** rather than by predicted points alone.

Scarcity decides the order because a position that blocks every formation makes
the rest of the plan worthless until it is filled. Value decides the choice
because when money is the binding constraint the metric that spends it well is
value, not quality.

#### Scenario: ordering and ranking
- **WHEN** one position blocks every formation **THEN** it is filled first
- **WHEN** two candidates fit the band **THEN** the one with more points per
  euro is chosen, even if the other scores higher
- *Verifies:* `test_the_plan_fills_the_positions_that_block_every_formation_first`,
  `test_the_plan_ranks_by_points_per_euro_when_money_is_the_constraint`

### Requirement: The plan never buys a goalkeeper

No plan SHALL include a goalkeeper, and `/emergencia` SHALL never target the
goalkeeper line in either mode.

A league rule the admin enforces: a manager's **only** goalkeeper cannot be
claused — the attempt is cancelled and penalised. No raid can leave a squad with
zero goalkeepers, and one is all an eleven needs, so the money is always better
spent elsewhere. The code states this rule in a comment today and contradicts it
in the intent resolution.

#### Scenario: a goalkeeper loss and a goalkeeper candidate
- **WHEN** the manager loses a goalkeeper **THEN** the reinforced line is never
  the goalkeeper line
- **WHEN** goalkeepers are among the affordable rivals **THEN** none enters the
  plan
- *Verifies:* `test_the_plan_never_buys_a_goalkeeper`,
  `test_emergencia_never_targets_the_goalkeeper_line`

### Requirement: The plan is proved and priced before it is offered

The preview SHALL show the eleven the plan would field and the cost of each
signing, and SHALL state plainly when the budget cannot reach a legal eleven
rather than presenting a partial plan as a recovery.

The plan SHALL keep a configured minimum cash balance **when it can complete
without it**, and SHALL spend into it when that balance is the difference
between fielding a legal eleven and not. Spending the floor SHALL be reported,
so the manager knows they are left without cover.

A plan that spends everything and still cannot field an eleven is worse than no
plan, because it looks like progress. The floor exists because the balance is
what lets a manager answer the next clausulazo — but a squad that cannot field
an eleven loses points every matchday, while an empty balance only costs the
chance to retaliate. Having a team comes first; the cushion is what is kept out
of what is left over, not a wall in front of the eleven.

#### Scenario: complete plan, incomplete plan, and the floor
- **WHEN** the plan restores an eleven **THEN** that eleven is shown with the
  per-signing cost
- **WHEN** the budget cannot restore an eleven **THEN** the plan says so and
  claims no eleven
- **WHEN** the plan completes without touching the floor **THEN** the floor is
  left intact
- **WHEN** the floor is the difference between an eleven and no eleven
- **THEN** it is spent, and the plan says so
- *Verifies:* `test_the_preview_shows_the_eleven_the_plan_would_field`,
  `test_the_plan_states_when_it_cannot_reach_a_legal_xi`,
  `test_the_cash_floor_is_kept_when_the_plan_completes_without_it`,
  `test_completing_the_eleven_wins_over_keeping_the_cash_floor`

### Requirement: One confirmation, sequential execution, honest reporting

An approved plan SHALL be executed one signing at a time, re-planning between
purchases against the balance and clause values that actually remain. A target
that has become unavailable SHALL be replaced only by a candidate in the same
position and within the amount already reserved for that hole, and the
substitution SHALL be reported. Nothing outside the confirmed plan's shape SHALL
ever be bought, and each signing's outcome SHALL be reported individually.

Clause values move and rivals sell: a plan approved thirty seconds ago can have
a hole in it by the third purchase, and a flow that discovered this by failing
would leave the squad half-rebuilt with the money already gone.

#### Scenario: a vanished target, and the reporting
- **WHEN** a target is no longer clausulable **THEN** it is replaced within its
  position and reserved amount, and the substitution is reported
- **WHEN** the plan finishes **THEN** every signing's outcome is reported
- **WHEN** no substitute fits the reserved amount **THEN** that hole is reported
  unfilled rather than paid for out of another hole's reserve
- *Verifies:* `test_a_vanished_target_is_replaced_within_its_reserved_amount`,
  `test_nothing_outside_the_confirmed_plan_is_ever_bought`,
  `test_execution_reports_the_outcome_of_every_signing`

## MODIFIED Requirements

### Requirement: Preview resolves or offers a selector

`preview_clausulazo` SHALL target the lost line directly when the loss is
unambiguous (one single-position loss). When ambiguous — a multi-position loss,
or several losses — it SHALL send a **selector** (buttons per candidate
position + a weakest-line fallback + cancel) and set no target yet. With no
losses it SHALL target the weakest line. `force_position` / `force_weakest`
SHALL skip detection entirely. When nothing is affordable it SHALL send a
no-target message with no buttons.

When the squad cannot field a legal eleven, rebuild mode SHALL take precedence
over every path above. Losses in the goalkeeper line SHALL be reported but SHALL
never be offered as a line to reinforce, and a `force_position` outside 1-4
SHALL be answered with a 400 rather than crashing.

Reporting goalkeeper losses is a repair, not a refinement: two of them currently
leave the flow with no outfield line to offer, fall through to the no-losses
branch, and answer *"sin clausulazos recientes contra ti"* — denying a raid that
just happened, at the moment the manager most needs to be believed.

#### Scenario: unambiguous single loss
- **WHEN** exactly one single-position DEF is lost
- **THEN** a DEF target is picked, with confirm/cancel buttons
  (`e:c:<player>:<owner>:<amount>`, `e:n`)
- *Verifies:* `test_preview_single_loss_targets_lost_line`

#### Scenario: ambiguous → selector
- **WHEN** the loss is multi-position, or there are multiple losses
- **THEN** a selector lists each position (`e:p:<pos>`), the weakest fallback
  (`e:m`) and cancel (`e:n`); no target is set yet
- *Verifies:* `test_preview_multi_pos_single_loss_shows_selector`,
  `test_preview_multiple_losses_shows_selector`

#### Scenario: forced entry points and no-losses fallback
- **WHEN** `force_position` / `force_weakest` is given, or there are no losses
- **THEN** detection is skipped / the weakest line is targeted
- *Verifies:* `test_preview_force_position_skips_detection`,
  `test_preview_force_weakest_skips_detection`,
  `test_preview_no_losses_uses_weakest_line`

#### Scenario: goalkeepers, a broken squad, and a bad parameter
- **WHEN** every loss is a goalkeeper **THEN** the losses are reported and no
  line is offered — never "no recent clausulazos"
- **WHEN** the squad cannot field a legal eleven **THEN** rebuild mode runs
  instead of the selector
- **WHEN** `force_position` is outside 1-4 **THEN** the route answers 400
- *Verifies:* `test_two_goalkeeper_losses_are_reported_not_silently_dropped`,
  `test_rebuild_mode_takes_precedence_over_the_selector`,
  `test_force_position_outside_the_range_is_a_400_not_a_crash`
