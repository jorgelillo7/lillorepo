# Capability: clausulazo-emergency

The `/emergencia` flow. When a manager loses a player to a clause
(clausulazo) and the squad can still field an eleven, it picks the best
affordable rival to clause back. When the squad cannot field one, it plans the
whole rebuild instead — the eleven plus two substitutes — and executes it
signing by signing. Both paths preview in Telegram and wait for an inline
confirmation before spending anything.

- **Source:** `packages/biwenger_tools/api/logic/emergency.py`,
  `clausulazo_detection.py`, `clausulazo_candidates.py`, `rebuild.py`,
  `rebuild_store.py`, `api/app.py`, `packages/biwenger_tools/bot/app.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_emergency.py`,
  `packages/biwenger_tools/api/tests/test_rebuild.py`,
  `packages/biwenger_tools/api/tests/test_rebuild_store.py`,
  `packages/biwenger_tools/api/tests/test_routes.py`,
  `packages/biwenger_tools/bot/tests/test_bot.py`

---

### Requirement: Detect the manager's recent losses

`recent_lost_players` SHALL return the manager's own clause losses from the
last 24h, matching the losing manager by user id, or by name when the board
payload omits the id. It SHALL surface every match (including multi-position
players, with their `alt_positions`) and ignore other managers' losses.

#### Scenario: match by id, by name, and window
- **WHEN** a clause names the manager by id / by name within 24h
- **THEN** the loss is returned; **AND** losses older than the 24h window or
  belonging to other managers are excluded
- *Verifies:* `test_recent_lost_players_matches_by_user_id`,
  `test_recent_lost_players_matches_by_name_when_id_missing`,
  `test_recent_lost_players_ignores_entries_older_than_24h`,
  `test_recent_lost_players_ignores_other_managers_losses`

### Requirement: Weakest outfield line

`weakest_outfield_position` SHALL return the outfield position (DEF/MID/FWD)
with the fewest players in the squad, breaking ties in the order DEF > MID >
FWD. Goalkeepers are never chosen.

#### Scenario: minimum count wins, DEF breaks ties
- **WHEN** the squad has 3 DEF / 2 MID / 1 FWD **THEN** the weakest is FWD
- **WHEN** counts tie **THEN** DEF wins, then MID
- *Verifies:* `test_weakest_outfield_position_picks_minimum_count`,
  `test_weakest_outfield_position_ties_prefer_def_then_mid`

### Requirement: Target selection

`pick_top_in_position` SHALL return the highest-SF candidate in the preferred
position; when that position has no candidate it SHALL fall back to the
highest-SF candidate overall and flag that it is out of position. With no
candidates it SHALL return `None`.

#### Scenario: in-position first, else top-SF fallback
- **WHEN** a DEF candidate (SF 500) and a higher FWD (SF 900) exist and DEF is
  preferred **THEN** the DEF is chosen, flagged in-position
- **WHEN** the preferred position is empty **THEN** the top-SF overall is
  chosen, flagged out-of-position
- *Verifies:* `test_pick_target_returns_top_sf_in_preferred_position`,
  `test_pick_target_falls_back_to_top_sf_when_position_empty`,
  `test_pick_target_returns_none_when_no_candidates`

### Requirement: The blend, when present, reaches every pool `/emergencia` builds

`preview_clausulazo`, `_preview_rebuild` and `execute_rebuild` SHALL build the
owner's own squad and the rival pool with the same Oráculo index and scale the
rest of the request uses. This flow decides which player to buy and how much
to pay for it, so once the blend moves a projection the recommendation SHALL
change accordingly — that is the intent of running a second opinion, not a
regression to guard against.

The two pools inside one request (the owner's rows and the rival pool feeding
`rebuild.build_plan`, or the projected eleven and the fresh rival read at
execution time) SHALL always share the same index and scale: they are compared
against each other within the same flow, and a mismatch would repeat
`league_compare`'s defect one level down — a plan priced against two different
scales.

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

### Requirement: Execute notifies on success and failure

`execute_clausulazo` SHALL place the clause via the SDK and send a success
message resolving the player name (falling back to the id when the player map
lacks it). On a Biwenger rejection it SHALL notify the failure and re-raise so
the caller returns an error.

#### Scenario: success and failure both notify
- **WHEN** the clause succeeds **THEN** an "ejecutado" message with the player
  name goes out (or "jugador <id>" when the name is unknown)
- **WHEN** the SDK raises **THEN** a "rechazado" message goes out and the error
  propagates
- *Verifies:* `test_execute_clausulazo_calls_sdk_and_notifies`,
  `test_execute_clausulazo_falls_back_to_id_when_player_missing_from_map`,
  `test_execute_clausulazo_notifies_and_raises_on_failure`

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

A plan with no signings at all — nothing affordable — SHALL NOT be persisted:
storing wipes any other plan already live for the season, and there is nothing
here worth confirming.

#### Scenario: complete plan, incomplete plan, and the floor
- **WHEN** the plan restores an eleven **THEN** that eleven is shown with the
  per-signing cost
- **WHEN** the budget cannot restore an eleven **THEN** the plan says so and
  claims no eleven
- **WHEN** the plan completes without touching the floor **THEN** the floor is
  left intact
- **WHEN** the floor is the difference between an eleven and no eleven
- **THEN** it is spent, and the plan says so
- **WHEN** the plan has no signings **THEN** it is not stored, and no
  confirmation is offered
- *Verifies:* `test_the_preview_shows_the_eleven_the_plan_would_field`,
  `test_the_plan_states_when_it_cannot_reach_a_legal_xi`,
  `test_the_cash_floor_is_kept_when_the_plan_completes_without_it`,
  `test_completing_the_eleven_wins_over_keeping_the_cash_floor`,
  `test_preview_rebuild_does_not_store_a_plan_with_no_signings`

### Requirement: One confirmation, sequential execution, honest reporting

An approved plan SHALL be executed one signing at a time, re-reading the
balance between purchases. A target
that has become unavailable SHALL be replaced only by a candidate in the same
position and at or under the price the plan approved for that signing
(`clause_at_plan` — the target's own price at plan time, not the cheapest-
candidate figure "reserved" in the requirement above), and the substitution
SHALL be reported. Nothing outside the confirmed plan's shape SHALL ever be
bought, and each signing's outcome SHALL be reported individually.

Clause values move and rivals sell: a plan approved thirty seconds ago can have
a hole in it by the third purchase, and a flow that discovered this by failing
would leave the squad half-rebuilt with the money already gone.

The eleven's holes and the bench's extra signings SHALL be tracked separately:
a re-check against the squad's current deficit SHALL apply to the eleven's
signings only. A bench signing carries no such hole — it SHALL be bought when
its exact target is still available at or under `clause_at_plan`, and reported
unavailable rather than substituted when it is not. Signings SHALL be
processed eleven-first regardless of storage order, so a bench purchase can
never consume the budget an eleven hole still needs.

Reporting an outcome, or reading the closing cash balance and eleven, SHALL
NOT abort a run that has already spent money: a delivery or read failure
after a purchase SHALL be logged and downgraded to a warning rather than
raised — by that point the purchase already happened, and losing the record
of it is worse than an incomplete notification.

#### Scenario: a vanished target, and the reporting
- **WHEN** a target is no longer clausulable **THEN** it is replaced within its
  position and at or under the price the plan approved for it, and the
  substitution is reported
- **WHEN** the plan finishes **THEN** every signing's outcome is reported
- **WHEN** no substitute fits that price **THEN** that hole is reported
  unfilled rather than paid for with money meant for another hole
- *Verifies:* `test_a_vanished_target_is_replaced_within_its_clause_at_plan`,
  `test_nothing_outside_the_confirmed_plan_is_ever_bought`,
  `test_execution_reports_the_outcome_of_every_signing`

#### Scenario: bench signings are bought on their own terms
- **WHEN** a bench signing's target is still available at or under its
  approved price **THEN** it is bought
- **WHEN** a bench signing's target is gone **THEN** it is reported
  unavailable, never substituted for a different body
- **WHEN** signings are processed **THEN** which rules apply to each is
  decided by its marker and never by its position in the stored list, so a
  bench signing never consumes an eleven's hole
- *Verifies:* `test_a_bench_signing_is_bought_on_its_own_terms_not_against_a_hole`,
  `test_a_bench_signing_is_reported_unavailable_not_swapped_for_a_decoy`,
  `test_bench_and_eleven_signings_are_told_apart_by_marker_not_by_list_order`

#### Scenario: reporting survives a downstream failure
- **WHEN** Telegram rejects a signing's or the summary's report **THEN** the
  run continues and no purchase already made is lost
- **WHEN** the closing eleven check or cash read fails **THEN** the summary
  still reports every purchase, with that one fact stated as unknown
- *Verifies:* `test_a_telegram_failure_after_a_purchase_does_not_abort_the_run`,
  `test_every_purchase_is_logged_even_if_telegram_never_hears_about_it`,
  `test_a_lineup_search_exhaustion_in_the_final_check_does_not_crash_execution`,
  `test_a_cash_read_failure_in_the_final_check_does_not_crash_execution`

### Requirement: An approved plan executes at most once, and only while it is fresh

Executing a plan SHALL claim it first, in a single transaction that reads and
removes it, so a second confirmation of the same plan reaches no external
service and spends nothing. Storing a new plan SHALL invalidate any other plan
still live for the season. A plan older than the configured TTL SHALL be
refused rather than executed. Before spending, execution SHALL re-read the
squad and buy nothing when it already fields a legal eleven, SHALL skip an
eleven signing whose hole has closed, and SHALL stop the run when a purchase
returns an unknown outcome rather than continue against a squad it can no
longer describe. No goalkeeper SHALL be bought at execution time either.

This is the money safety of the whole feature, and it is worth stating rather
than leaving to the code: Telegram makes a second tap easy, a plan priced
thirty minutes ago is priced against a market that has moved, and a purchase
whose reply was lost is a purchase whose outcome nobody knows — continuing past
it would spend against a squad the code has already got wrong.

#### Scenario: a second tap, a stale plan, and a squad that recovered
- **WHEN** the same plan is confirmed twice **THEN** the second call reaches no
  external service
- **WHEN** the plan is older than the TTL **THEN** it is refused
- **WHEN** the squad already fields a legal eleven **THEN** nothing is bought
- **WHEN** an eleven signing's hole has closed **THEN** that signing is skipped
- **WHEN** a purchase returns an unknown outcome **THEN** the run stops and the
  rest are reported as not attempted
- **WHEN** a goalkeeper is the best substitute available **THEN** it is not
  bought
- *Verifies:* `test_a_second_execute_rebuild_call_never_reaches_biwenger_again`,
  `test_execute_rebuild_refuses_a_plan_older_than_the_ttl`,
  `test_execute_rebuild_buys_nothing_when_the_squad_already_fields_an_eleven`,
  `test_a_signing_is_skipped_when_its_hole_no_longer_exists`,
  `test_an_unknown_outcome_stops_the_loop_and_the_rest_are_not_attempted`,
  `test_execute_rebuild_never_buys_a_goalkeeper_as_a_substitute`

### Requirement: The non-aggression pact binds every path that spends money

The owner keeps a per-**manager** non-aggression pact in `pactos/actual`,
edited from the bot's `/pacto`. No flow of `/emergencia` SHALL propose or buy a
player owned by a manager in it. The pact SHALL be applied at all three pool
sites, because all three can put money on a player:

1. the single-pick preview, before `pick_top_in_position`;
2. the rebuild preview, before `rebuild.build_plan`;
3. **rebuild execution**, whose `else` branch re-picks a substitute when the
   approved player is gone — a plan approved before a manager joined the pact
   must not sign around it.

Manager ids SHALL be compared as integers, so a pact document written with
string ids still matches rather than silently protecting nobody.

#### Scenario: the best candidate is a friend
- **WHEN** the highest-SF player in the needed line belongs to a pacted manager
- **THEN** the target is the next best unpacted candidate
- *Verifies:* `test_preview_skips_a_pacted_managers_player_for_the_next_best`

#### Scenario: a rebuild plan never signs a pacted manager's player
- **WHEN** the squad cannot field an eleven and every affordable rival is pacted
- **THEN** `build_plan` receives an empty pool
- *Verifies:* `test_rebuild_plan_never_signs_a_pacted_managers_player`

### Requirement: An empty pool says whether the pact caused it

When the pact removed candidates and nothing is left to buy, the "sin
candidatos" message SHALL name the pact, count the excluded candidates and
point at `/pacto`. It SHALL stay silent about the pact when nothing was
excluded.

Without this an owner with a broken eleven and cash in hand reads "sin
candidatos asequibles" and goes looking for money they already have. The lever
is `/pacto`, so the message says so.

#### Scenario: the pact is the only thing blocking the buy
- **WHEN** every affordable rival belongs to a pacted manager
- **THEN** the message names the pact and reports the excluded count
- **WHEN** nothing was excluded **THEN** the message does not mention it
- *Verifies:* `test_no_target_message_names_the_pact_when_it_is_what_emptied_the_pool`,
  `test_no_target_message_stays_quiet_when_no_one_was_excluded`,
  `test_preview_reports_the_pact_when_it_leaves_nothing_to_buy`

### Requirement: The pact is one document, outlives the season, toggled whole

`pact_store` SHALL hold the pact as a single `pactos/actual` document with a
`manager_ids` list, `load` returning an empty set when it does not exist — a
league without a pact is the normal case, not an error.

It SHALL NOT be keyed by season, unlike `rebuild_store`. A rebuild plan belongs
to the deficit that produced it; an agreement with a rival is standing. Season
-keyed, the pact would empty itself at each rollover silently and fail **open**
— the new year's first `/emergencia` proposing the very manager it protects. It
changes when the owner changes it, and at no other moment. `toggle` SHALL flip one
manager and return whether they ended up protected, so the bot redraws from the
return value in one round trip. An unparseable id SHALL be dropped with a
warning rather than raised: one junk entry must not blind the whole pact.

#### Scenario: load, toggle and survive junk
- **WHEN** the document is read **THEN** its id carries no season
- **WHEN** no document exists **THEN** `load` returns an empty set
- **WHEN** the document holds `[10, "", None]` **THEN** `load` returns `{10}`
- **WHEN** `toggle` runs on a manager in / not in the pact
- **THEN** it removes / adds them and returns False / True
- *Verifies:* `test_the_pact_is_not_scoped_to_a_season`,
  `test_load_returns_an_empty_set_when_no_pact_was_ever_saved`,
  `test_load_survives_a_document_with_a_junk_id`,
  `test_toggle_adds_a_manager_that_was_not_in_the_pact`,
  `test_toggle_removes_a_manager_that_was_already_in_the_pact`
