# Capability: clausulazo-emergency

The `/emergencia` flow: when a manager loses a player to a clause (clausulazo),
help them strike back by picking the best affordable rival player to clause,
with a Telegram preview + inline confirmation before executing.

- **Source:** `packages/biwenger_tools/api/logic/emergency.py`,
  `clausulazo_detection.py`, `clausulazo_candidates.py`, `api/app.py`
- **Verified by:** `packages/biwenger_tools/api/tests/test_emergency.py`,
  `packages/biwenger_tools/api/tests/test_routes.py`

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

### Requirement: Preview resolves or offers a selector

`preview_clausulazo` SHALL target the lost line directly when the loss is
unambiguous (one single-position outfield loss). When ambiguous — a
multi-position loss, or several losses — it SHALL send a **selector**
(buttons per candidate position + a weakest-line fallback + cancel) and set
no target yet. With no losses it SHALL target the weakest line.
`force_position` / `force_weakest` SHALL skip detection entirely, and a
`force_position` outside the outfield range (2-4) SHALL be rejected with a
400 rather than reach the flow. When nothing is affordable it SHALL send a
no-target message with no buttons.

The goalkeeper line is never a resolved intent. Biwenger allows a manager's
last goalkeeper to be claused; the league does not, and the admin cancels the
operation and penalises whoever tried — so no raid leaves anyone without one,
and one is all a legal eleven needs. There is no goalkeeper line to reinforce. A single goalkeeper loss SHALL fall back to the weakest
outfield line instead; a batch of losses that are all goalkeepers SHALL be
reported by name rather than folded into "no recent losses".

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

#### Scenario: nothing affordable
- **WHEN** no candidate fits the cash
- **THEN** a "Sin candidatos" message is sent with no buttons and target `None`
- *Verifies:* `test_preview_no_affordable_candidates_sends_no_target_message`

#### Scenario: the goalkeeper line is never the resolved intent
- **WHEN** the only recent loss is a goalkeeper
- **THEN** the weakest outfield line is targeted instead, with a reason
  naming the lost goalkeeper
- **WHEN** every recent loss is a goalkeeper (single or several)
- **THEN** the losses are reported by name with no target and no selector,
  instead of being reported as "no recent losses"
- *Verifies:* `test_emergencia_never_targets_the_goalkeeper_line`,
  `test_two_goalkeeper_losses_are_reported_not_silently_dropped`

#### Scenario: force_position outside the outfield range is rejected
- **WHEN** `force_position` is not one of 2/3/4 (garbage, negative, or the
  goalkeeper line)
- **THEN** the route answers 400 without calling into the flow
- *Verifies:* `test_force_position_outside_the_range_is_a_400_not_a_crash`

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
