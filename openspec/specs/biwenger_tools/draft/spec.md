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
from the live market. The file is read from a public bucket object and decoded
as `utf-8-sig` explicitly — the bucket serves it without a charset, and the
HTTP default of ISO-8859-1 would mangle every accented name and the
BOM-prefixed first header, silently dropping a third of the market.

Rows SHALL be joined to Biwenger player ids by normalised name, disambiguated
by team when two players share a name, and any row that still cannot be
resolved SHALL be reported rather than silently dropped. The joined market
SHALL be cached per instance: it cannot change mid-draft, and re-reading it
would add two network round-trips to every pick.

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
- **WHEN** the Biwenger call fails **THEN** the pick is never finalised blindly
- *Verifies:* `test_gate_off_never_calls_biwenger_transfer_or_board`,
  `test_submit_pick_applies_with_gate_off`,
  `test_gate_on_calls_biwenger_transfer_and_resolves_offer_id`

---

### Requirement: A dropped transfer is verified, not guessed

A connection lost mid-POST is ambiguous: Biwenger may have applied the transfer
and only the response gone missing. The endpoint carries no idempotency key, so
guessing either buys the player twice or strands the pick.

On failure the service SHALL read the manager's squad and act on what it finds:

| Player owned? | Slot | Told to the group |
|---|---|---|
| No | freed (`reverted`) | retry yourself |
| Yes | finalised (`applied`) | pick stands |
| Unknown | left `reserved` | call the admin |

The transfer SHALL NOT be retried in any branch. The rejection message SHALL
match what the manager can actually do — telling him to retry while the slot is
still reserved sends him at the one action guaranteed to fail.

#### Scenario: verify before deciding
- **WHEN** the squad read shows the player is not owned **THEN** the slot is freed and
  the manager can pick again unaided
- **WHEN** the squad read shows the player is owned **THEN** the pick is finalised without
  a second transfer
- **WHEN** the squad read itself fails **THEN** the slot stays blocked for the admin
- *Verifies:* `test_failed_transfer_frees_the_slot_when_it_did_not_land`,
  `test_failed_transfer_finalises_when_the_response_was_lost`,
  `test_failed_transfer_blocks_when_it_cannot_be_verified`

---

### Requirement: A pick that is not applied costs Biwenger nothing

Biwenger rate-limits the whole league, not one client, and a session costs two
requests to open (login + `/account`). The session SHALL therefore be built only
once a slot is reserved and a transfer is certain — never to validate a turn,
resolve a name, or answer a duplicate.

Resolving the market SHALL use the public competition endpoint, which needs no
session, and SHALL download it once per load rather than once per map.

The session SHALL be reused across picks. Biwenger's quota, read off the `429`
headers, is `x-rate-limit-limit: 500` per account over an 8-hour window, and 15
rounds of 7 managers is 105 picks — logging in per pick would spend the window
before the draft ends. (Whether the window slides on each request while over
quota is unconfirmed: one observation showed the reset land exactly 8h after the
probe rather than 8h after the burst, but distinguishing the two costs the very
requests that would move it.) A
rejected token SHALL be re-authenticated once, which is safe because a `401` is
refused before Biwenger applies anything.

#### Scenario: rejected picks make no request
- **WHEN** a pick is rejected out of turn, names an unknown player, or is ambiguous
  **THEN** no Biwenger session is opened
- **WHEN** the market is loaded **THEN** the competition payload is fetched exactly once
- **WHEN** consecutive picks are applied **THEN** they share one authenticated session
- **WHEN** the token is rejected **THEN** the session is rebuilt once and the call retried
- *Verifies:* `test_rejected_pick_never_authenticates`,
  `test_get_competition_maps_downloads_once`,
  `test_consecutive_picks_authenticate_once`,
  `test_rejected_token_re_authenticates_once`

---

### Requirement: Each turn is timed

The bot SHALL record when a turn opens and how long the manager took, and
report the wait in the pick confirmation. `turn_started_at` lives on the state
document but NOT on `DraftState`: the pure engine has no business knowing about
clocks. It SHALL be written in the same `set` as the state — that call replaces
the whole document, so a separate write would be erased by the next pick.

The opening pick has no preceding turn and SHALL report no wait rather than an
invented one. An undo SHALL restart the clock: it is an admin action, and the
manager should not be charged for however long it took someone to notice.

The per-manager report SHALL use the **median**, not the mean — a draft spans
nights, and one turn that opened at 3am would otherwise decide the ranking.

#### Scenario: measuring a turn
- **WHEN** the first pick of the draft is applied **THEN** no wait is reported or stored
- **WHEN** any later pick is applied **THEN** the wait since the previous pick is stored
  and shown
- **WHEN** consecutive picks are applied **THEN** the clock survives each state write
- **WHEN** a pick is undone **THEN** the clock restarts from that moment
- *Verifies:* `test_first_pick_reports_no_wait`,
  `test_second_pick_measures_the_wait`,
  `test_state_write_keeps_the_clock_alive_across_picks`,
  `test_undo_restarts_the_clock`,
  `test_format_wait_uses_the_coarsest_useful_unit`

---

### Requirement: The draft has an explicit lifecycle

The draft SHALL be opened by publishing the frozen market CSV and closed when
the last pick lands. While closed, every operation that writes to Biwenger —
picking and undoing — SHALL be rejected.

The reason is that `/deshacer` is a real `release_player` + `apply_bonus`
against real money. Once the season is under way that is not an undo, it is
selling a player mid-season.

The lifecycle record SHALL live in its own document, NOT on the turn state:
the state document is replaced wholesale on every pick, so anything stored
alongside it is erased by the next one.

A draft with no lifecycle record SHALL be treated as open. The guard exists to
stop writes after the last pick, not to demand a ceremony that drafts already
running never performed.

Opening SHALL stamp `turn_started_at`, so the first pick has something to
measure its wait against.

Closing SHALL also be reachable outside the api. Inside it, closing happens only
as a side effect of the final pick, so a draft whose last pick lands under a
revision that predates this behaviour would stay open forever — and an open
finished draft still accepts `/deshacer`, which sells a player mid-season.

The season's history — the readable record and the machine-readable
availability model the next draft reads — SHALL be written by that same
out-of-api close. The api runs in Cloud Run and cannot write to the repository,
so nothing else will produce it.

#### Scenario: opening and closing
- **WHEN** the draft is opened **THEN** the starting instant is stamped and the group
  is greeted
- **WHEN** the final pick is applied **THEN** the draft closes itself
- **WHEN** a pick or an undo is attempted on a closed draft **THEN** it is rejected and
  Biwenger is never contacted
- **WHEN** no lifecycle record exists **THEN** the draft behaves as open
- **WHEN** a pick is applied **THEN** the lifecycle record survives the state write
- *Verifies:* `test_the_final_pick_closes_the_draft`,
  `test_a_closed_draft_rejects_picks_and_undo`,
  `test_a_draft_with_no_lifecycle_record_stays_open`,
  `test_reopening_stamps_the_starting_instant`,
  `test_a_pick_does_not_wipe_the_lifecycle_record`

#### Scenario: closing from outside the api
- **WHEN** `scripts/draft/close.py --write` runs on a finished draft **THEN** the draft
  is closed, the season history is written and the group is told
- **WHEN** it runs on a draft the api already closed **THEN** it writes the history
  anyway, because that path produces no files
- **WHEN** it runs with picks still pending **THEN** it refuses unless `--force` is
  passed with a reason
- *Verifies:* operational script, exercised by its own dry run

---

### Requirement: The last pick can be undone by the admin

`/deshacer` SHALL be restricted to the configured draft admin, identified by a
Telegram **user** id — always positive, and therefore never derivable from the
owner chat id, which belongs to a group and is negative.

Undo SHALL be a `release_player` (transfer back to free agency) followed by an
`apply_bonus` refund, in that order, and SHALL NOT use `revertOffer`. Biwenger
issues no identifier for an admin transfer — the POST answers `204` with an
empty body and no useful headers, and `adminTransfer` board entries carry no
`id` field even when one is requested explicitly — so there is nothing to
revert *by*. Release goes first because a player left unowned is visible on the
board, whereas a refund without a release would silently pay twice.

Undo SHALL rewind the turn to the manager whose pick was removed, restore the
budget, and be chainable: repeating it walks back one pick at a time.

#### Scenario: undo permissions
- **WHEN** a non-admin calls undo **THEN** it is refused
- **WHEN** there are no picks **THEN** it is refused
- *Verifies:* `test_undo_rejects_non_admin`, `test_undo_rejects_when_no_picks`

#### Scenario: undo releases the player and refunds the price
- **WHEN** an applied pick is undone
- **THEN** the player is released to free agency and the exact price is
  refunded to its buyer alone, without any call to `revert_transfer`
- **WHEN** the pick never reached Biwenger (gate off) **THEN** only state rewinds
- *Verifies:* `test_undo_releases_the_player_and_refunds_the_price`,
  `test_undo_works_without_an_offer_id`, `test_undo_reverts_last_pick_gate_off`

#### Scenario: the turn rewinds and undo chains
- **WHEN** three picks are undone in a row
- **THEN** the turn walks back one at a time and every budget is restored
- **WHEN** the manager re-picks into the slot just freed
- **THEN** it is accepted — a `reverted` slot is free, only `reserved` and
  `applied` block a second call
- *Verifies:* `test_chained_undos_rewind_the_turn_one_pick_at_a_time`,
  `test_undo_then_repick_reuses_the_same_slot`

---

### Requirement: Registration is offered as a picker

`/soy` with no name SHALL answer with one button per draft manager rather than
an error: Telegram sends a bare command when it is tapped from the `/` menu, so
the argument-less form is the common path, not the exceptional one. Managers
already claimed SHALL be marked but stay selectable, so a mis-tap is fixable
without an admin. `/pick` with no player SHALL likewise explain itself.

#### Scenario: the picker
- **WHEN** `/soy` arrives with no argument **THEN** the manager buttons are posted
- **WHEN** a button is tapped **THEN** that manager is registered by id
- **WHEN** `/pick` arrives with no argument **THEN** the bot asks for a player
  and calls no endpoint
- *Verifies:* `test_bare_soy_posts_the_manager_picker_instead_of_failing`,
  `test_soy_picker_tap_registers_that_manager`,
  `test_bare_pick_asks_for_a_player_without_calling_the_api`

---

### Requirement: The export is readable in the group

`/exportar` SHALL send one message per manager, each listing that squad's
picks with prices and the budget left. A single block would exceed Telegram's
4096-character limit at full draft size, and a squad is the unit a reader
wants whole. The api decides where the seams go; the bot only relays them.

#### Scenario: per-manager blocks
- **WHEN** picks exist **THEN** one block per manager with picks is returned
- **WHEN** none exist **THEN** no blocks are sent
- *Verifies:* `test_export_picks_renders_one_message_per_manager`,
  `test_export_picks_with_nothing_yet_sends_no_blocks`,
  `test_exportar_sends_one_message_per_manager_block`
