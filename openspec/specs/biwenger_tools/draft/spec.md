# Capability: draft

The annual snake draft, arbitrated by the Telegram bot. Managers call their
picks in a supergroup; the bot enforces turn order, budget and squad
composition, records every pick in Firestore, and — behind a gate — applies the
transfer in Biwenger.

- **Source:** `packages/biwenger_tools/api/logic/draft.py` (pure engine),
  `api/logic/draft_service.py` (persistence + orchestration),
  `api/app.py` (`/draft/*`), `packages/biwenger_tools/bot/app.py` (group routing),
  `core/sdk/biwenger.py` (admin operations)
- **Verified by:** `api/tests/test_draft.py`, `api/tests/test_draft_service.py`,
  `bot/tests/test_bot.py`

---

### Requirement: The draft group is isolated from the admin surface

The bot SHALL route by chat id. The owner's private chat keeps the full admin
command set; the draft supergroup SHALL expose only the draft commands. No
admin command or admin callback prefix may be invoked from the group, and the
reply-keyboard label router SHALL NOT be consulted for group messages — plain
group chatter must never trigger an action.

#### Scenario: group cannot reach admin commands
- **WHEN** an admin command or an `e:`/`o:`/`analizar:` callback arrives from the draft group
- **THEN** it is refused
- **WHEN** a group message matches a reply-keyboard label
- **THEN** the label router is not consulted
- *Verifies:* `test_admin_command_from_draft_group_is_refused`,
  `test_admin_callback_prefix_from_draft_group_is_refused`,
  `test_group_message_does_not_consult_label_dispatch`

#### Scenario: unknown chats and service messages
- **WHEN** a draft command arrives from an unrecognised chat **THEN** it is dropped
- **WHEN** a Telegram service message with empty text arrives **THEN** it is ignored
- *Verifies:* `test_draft_command_from_unknown_chat_is_dropped`,
  `test_draft_callback_from_unknown_chat_is_dropped`,
  `test_service_message_with_empty_text_is_ignored`

---

### Requirement: Only registered managers may pick

The group contains both managers and spectators. `/soy <nombre>` SHALL resolve
a free-text name to a league manager and record the mapping; the registration
map is the whitelist. A name that is not part of the draft order SHALL be
rejected, and an unregistered Telegram user SHALL NOT be able to pick.

#### Scenario: registration and rejection
- **WHEN** a known manager name is given (exact or unambiguous prefix) **THEN** it registers
- **WHEN** the name is unknown, or belongs to a spectator outside the draft order
- **THEN** it is rejected
- **WHEN** an unregistered user runs `/pick` **THEN** it is rejected
- *Verifies:* `test_register_manager_resolves_exact_name`,
  `test_register_manager_resolves_unambiguous_prefix`,
  `test_register_manager_rejects_unknown_name`,
  `test_register_manager_rejects_spectator_not_in_draft_order`,
  `test_submit_pick_rejects_unregistered_user`

---

### Requirement: Snake order determines whose turn it is

Turn order SHALL follow a snake over the season's manager order: the direction
reverses every round. Pick number and `(round, position, manager)` SHALL be
exact inverses of one another. A pick out of turn SHALL be rejected.

#### Scenario: snake ordering and its round boundary
- **WHEN** mapping pick numbers across a round boundary
- **THEN** the manager sequence reverses while the in-round position keeps ascending
- *Verifies:* `test_pick_number_to_slot_round_2_is_reversed`,
  `test_pick_number_to_slot_round_boundary_off_by_one`,
  `test_slot_to_pick_number_is_inverse_of_pick_number_to_slot`,
  `test_draft_order_sequence_alternates_direction_each_round`,
  `test_submit_pick_rejects_out_of_turn`, `test_validate_pick_rejects_wrong_turn`

---

### Requirement: Budgets are per manager and must stay feasible

Every manager starts on a base budget with per-manager overrides, keyed by
manager and never by draft position — the order is inverse to the standings and
changes every season. Beyond simple affordability, a pick SHALL be rejected
when it would leave too little money to fill the remaining squad slots at the
cheapest available prices.

#### Scenario: affordability and feasibility
- **WHEN** the price exceeds the remaining budget **THEN** rejected as `INSUFFICIENT_BUDGET`
- **WHEN** the pick would leave the remaining slots unfillable
- **THEN** rejected as `BUDGET_INFEASIBLE`
- *Verifies:* `test_build_budgets_applies_override_on_top_of_base`,
  `test_default_budget_overrides_apply_to_exactly_one_manager`,
  `test_validate_pick_rejects_insufficient_budget`,
  `test_validate_pick_rejects_budget_infeasible_near_end_of_draft`,
  `test_validate_pick_accepts_when_budget_feasibility_holds`

---

### Requirement: The squad must remain completable

A squad is 15 players that can field a valid XI plus at least one substitute
per line. A pick SHALL be rejected when the resulting counts could no longer
reach a valid composition with the slots that remain.

#### Scenario: composition reachability
- **WHEN** the final slot would leave a line uncoverable
- **THEN** rejected as `COMPOSITION_INFEASIBLE`
- *Verifies:* `test_composition_ok_false_with_only_one_goalkeeper`,
  `test_composition_reachable_false_with_negative_slots`,
  `test_validate_pick_rejects_composition_infeasible_on_final_slot`,
  `test_validate_pick_rejects_when_squad_already_full`

---

### Requirement: Free-text player names resolve, or ask

Managers type shorthand. A query SHALL resolve to a single player when
unambiguous, and otherwise return ranked candidates which the bot renders as
inline buttons. Confirming a candidate SHALL be possible only for the user who
ran `/pick`.

#### Scenario: resolution and disambiguation
- **WHEN** the query matches exactly one player **THEN** it resolves
- **WHEN** several players match **THEN** ranked candidates are returned and rendered as buttons
- **WHEN** a different user taps the confirm button **THEN** it is refused
- *Verifies:* `test_resolve_player_name_prefix_shorthand_resolves_uniquely`,
  `test_resolve_player_name_ambiguous_team_hint_returns_ranked_candidates`,
  `test_submit_pick_ambiguous_query_returns_candidates`,
  `test_pick_ambiguous_renders_candidate_keyboard`,
  `test_draft_pick_confirm_rejects_different_user`,
  `test_draft_pick_confirm_succeeds_for_requesting_user`

---

### Requirement: Prices come from the frozen market export

Prices SHALL come from the closed-market CSV exported on the agreed day, never
from the live market. Rows SHALL be joined to Biwenger player ids by normalised
name, disambiguated by team when two players share a name, and any row that
still cannot be resolved SHALL be reported rather than silently dropped.

#### Scenario: parsing and joining the export
- **WHEN** the CSV is parsed **THEN** its BOM and `;` delimiter are handled
- **WHEN** two players share a name **THEN** the team breaks the tie
- **WHEN** a row cannot be resolved **THEN** it is reported as unmatched
- *Verifies:* `test_load_market_csv_parses_bom_and_semicolons`,
  `test_join_market_to_biwenger_matches_by_normalised_name`,
  `test_join_market_to_biwenger_reports_unmatched_rows_instead_of_dropping`,
  `test_join_market_to_biwenger_reports_ambiguous_names_as_unmatched`

---

### Requirement: A pick is applied at most once

The Biwenger admin endpoints are non-idempotent deltas: they return `204` with
no body and carry no idempotency key, so a repeat call would both re-assign the
player and charge again. Telegram also retries webhooks. Each pick SHALL
therefore be reserved under a deterministic Firestore document id inside a
transaction, and a request for a slot that is already `reserved` or `applied`
SHALL NOT reach Biwenger a second time.

#### Scenario: duplicates never reach Biwenger
- **WHEN** the same pick is submitted twice, whether the first is `applied` or left `reserved` by a crash
- **THEN** no second transfer call is made
- **WHEN** two reservations race for the same slot **THEN** the second is rejected
- *Verifies:* `test_duplicate_applied_pick_does_not_recall_biwenger`,
  `test_duplicate_reserved_pick_rejects_without_calling_biwenger`,
  `test_retried_submit_pick_after_reserve_before_finalize_skips_biwenger`,
  `test_reserve_pick_rejects_second_reservation_of_same_slot`

---

### Requirement: Biwenger writes are gated

`DRAFT_APPLY_TO_BIWENGER` SHALL default to false. With the gate off the draft
runs fully — validation, turn order, Firestore, group replies — while making no
mutating Biwenger call at all. Read-only player lookups still run so that
player ids stay identical between a rehearsal and the live session.

#### Scenario: gate off and on
- **WHEN** the gate is off **THEN** no transfer, revert or board call is made
- **WHEN** the gate is on **THEN** the transfer is applied and the `offer_id` resolved
- **WHEN** the Biwenger call fails **THEN** the pick stays reserved and is rejected
- *Verifies:* `test_gate_off_never_calls_biwenger_transfer_or_board`,
  `test_submit_pick_applies_with_gate_off`,
  `test_gate_on_calls_biwenger_transfer_and_resolves_offer_id`,
  `test_gate_on_biwenger_failure_keeps_pick_reserved_and_rejects`

---

### Requirement: The last pick can be undone by the admin

`/deshacer` SHALL be restricted to the configured draft admin. Undo uses
Biwenger's own `revertOffer`, which returns the player to the pool and refunds
the price in a single call. Because the transfer responds `204` with no body,
the `offer_id` is recovered best-effort from the transfer board; when it could
not be recovered the undo SHALL say so rather than pretend to have worked.

#### Scenario: undo permissions and behaviour
- **WHEN** a non-admin calls undo **THEN** it is refused
- **WHEN** there are no picks **THEN** it is refused
- **WHEN** the pick was applied and has an `offer_id` **THEN** `revert_transfer` is called
- **WHEN** the `offer_id` is missing **THEN** the undo refuses and reports it
- *Verifies:* `test_undo_rejects_non_admin`, `test_undo_rejects_when_no_picks`,
  `test_undo_reverts_last_pick_gate_off`,
  `test_undo_calls_revert_transfer_when_applied_with_offer_id`,
  `test_undo_refuses_when_offer_id_missing`
