# Capability: telegram-commands

The Biwenger Telegram bot: a secured webhook that routes slash commands and
keyboard taps to the `api` service, and handles inline-keyboard callbacks for
the emergency and offers flows.

- **Source:** `packages/biwenger_tools/bot/app.py`, `api_client.py`, `menu.py`
- **Verified by:** `packages/biwenger_tools/bot/tests/test_bot.py`

---

### Requirement: Webhook is secret- and chat-gated

The webhook SHALL reject a wrong secret token (401) and silently ignore
(200, no action) updates from an unauthorised chat id — for both messages and
callback queries — so a leaked bot link cannot drive it.

#### Scenario: gates
- **WHEN** the secret is wrong **THEN** 401
- **WHEN** the chat id is not the configured one (message or callback)
- **THEN** silently ignored
- *Verifies:* `test_wrong_secret_returns_401`, `test_correct_secret_returns_200`,
  `test_wrong_chat_id_is_silently_ignored`,
  `test_wrong_chat_callback_is_silently_ignored`

### Requirement: Commands route to the API

Text commands SHALL map to the corresponding `api` call (parsing a `@botname`
suffix), `/preview` SHALL call auto-pick with `?dry_run=1` — which reports
the difference against the saved lineup rather than proposing one — and an API
failure
SHALL send an error message with the exception HTML-escaped inside `<code>`.

#### Scenario: routing, dry-run, and safe errors
- **WHEN** a text command (incl. `@botname`) is received **THEN** the mapped
  API endpoint is called; `/preview` adds `dry_run=1`
- **WHEN** the API call fails **THEN** an error message is sent with the
  exception HTML-escaped
- *Verifies:* `test_text_command_calls_api`,
  `test_command_with_botname_suffix_routes_correctly`,
  `test_preview_text_command_calls_api_with_dry_run`,
  `test_api_call_failure_sends_error_message`,
  `test_api_call_failure_html_escapes_exception_message`

### Requirement: Menu keyboard and analizar picker

`/menu` (and `/start`) SHALL attach the persistent reply keyboard; its labels
SHALL dispatch the same actions as the commands. `/analizar` (command or label)
SHALL open a manager picker rather than calling `/teams` directly, and SHALL
tell the user when the managers list is unreachable. The `🤝 Pacto` button
SHALL open the same pact picker as `/pacto`. Every menu button SHALL resolve to
either an api route or a picker — a button with neither is dead on tap.

#### Scenario: keyboard and picker
- **WHEN** `/menu` or `/start` **THEN** the persistent keyboard is sent
- **WHEN** a keyboard label is tapped **THEN** the mapped action fires
- **WHEN** `/analizar` **THEN** a manager picker opens; a manager tap calls
  `/teams?manager=<id>`, the TODOS tap calls `/teams` with no filter
- **WHEN** the managers fetch fails **THEN** the user is told
- **WHEN** `🤝 Pacto` is tapped **THEN** the pact picker opens, no api action
- **WHEN** the menu is built **THEN** no button lacks a destination
- *Verifies:* `test_menu_sends_persistent_reply_keyboard`, `test_start_aliases_menu`,
  `test_reply_keyboard_label_dispatches_action`,
  `test_reply_keyboard_analizar_label_opens_picker`,
  `test_analizar_text_command_opens_manager_picker`,
  `test_analizar_text_command_handles_manager_fetch_failure`,
  `test_analizar_id_callback_calls_teams_with_filter`,
  `test_analizar_all_callback_calls_teams_without_filter`,
  `test_reply_keyboard_pacto_label_opens_the_pact_picker`,
  `test_every_menu_button_has_somewhere_to_go`

### Requirement: Emergency callbacks

The `e:` inline callbacks SHALL drive the clausulazo flow: `e:c:<player>:<owner>:<amount>`
executes, `e:p:<pos>` refines with `force_position`, `e:m` with `force_weakest`,
`e:n` cancels (edits message, no API call). Malformed payloads SHALL be ignored
without hitting the API.

#### Scenario: confirm, refine, cancel, malformed
- **WHEN** each `e:` callback fires **THEN** it maps to the right API call
- **WHEN** `e:n` **THEN** the message is edited and no API call is made
- **WHEN** the payload is malformed (`e:c:not_a_number`) **THEN** ignored
- *Verifies:* `test_emergencia_confirm_callback_calls_execute_with_query_params`,
  `test_emergencia_selector_position_callback_refines_with_force_position`,
  `test_emergencia_selector_weakest_callback_refines_with_force_weakest`,
  `test_emergencia_cancel_callback_edits_message_and_does_not_call_api`,
  `test_emergencia_confirm_with_malformed_payload_is_ignored`,
  `test_unknown_callback_prefix_is_ignored`

### Requirement: Offers callbacks

The `o:` inline callbacks SHALL decide received offers: `o:a:<id>` accepts,
`o:r:<id>` rejects (with a "⏳ Rechazando…" toast), `o:i:<id>` ignores (strips
the keyboard, edits to "ignorada", no API call). Malformed or non-integer ids
SHALL be ignored without hitting the API.

#### Scenario: accept, reject, ignore, malformed
- **WHEN** `o:a` / `o:r` **THEN** POST decide accepted / rejected, keyboard stripped
- **WHEN** `o:i` **THEN** the message is edited, no API call
- **WHEN** the id is garbage or non-int **THEN** ignored
- *Verifies:* `test_ofertas_accept_callback_posts_decide_accepted`,
  `test_ofertas_reject_callback_posts_decide_rejected`,
  `test_ofertas_ignore_callback_edits_message_and_does_not_call_api`,
  `test_ofertas_malformed_callback_is_ignored`,
  `test_ofertas_non_int_offer_id_is_ignored`

### Requirement: `/pacto` edits the non-aggression pact

`/pacto` SHALL open an inline picker with one toggle per **rival** manager —
the owner's own row is absent, since there is no pact with yourself — labelled
🤝 when protected and ⚔️ when fair game. A `pact:<manager_id>` tap SHALL relay
to `POST /pact/toggle` and redraw the picker **in place**, so editing several
managers stays one message.

The bot SHALL hold no pact state of its own: it renders what the api returns
and relays taps, per the zero-logic bot rule. A malformed manager id SHALL be
ignored without hitting the API, and an unreachable `/pact` SHALL say so rather
than post an empty keyboard.

Every step SHALL acknowledge itself before the work starts, because the picker
sits behind a cold start plus a Biwenger league call:

- `/pacto` SHALL post a "procesando…" line and fetch in the **background**.
  Fetching inline blocks the worker past Telegram's timeout, which is how a
  slow call becomes a retried webhook and a duplicate picker.
- A `pact:` tap SHALL ack with a toast, the only feedback between the tap and
  the redraw.
- The redraw SHALL use the list `POST /pact/toggle` already returns, never a
  second `GET /pact` — re-fetching paid for a second Biwenger round trip on
  every tap, and made the button feel like it had not registered.

#### Scenario: open, toggle, redraw, reject junk
- **WHEN** `/pacto` **THEN** one `pact:<id>` button per rival, marked 🤝 / ⚔️
- **WHEN** `/pacto` **THEN** a "procesando…" line precedes the picker
- **WHEN** `pact:<id>` is tapped **THEN** the ack carries a toast, `/pact/toggle`
  is posted once, `/pact` is **not** re-read, and the same message is edited
  with the refreshed keyboard
- **WHEN** the id is not an integer **THEN** ignored, no API call
- **WHEN** `/pact` is unreachable **THEN** "No pude cargar el pacto"
- *Verifies:* `test_pacto_command_opens_the_pact_picker`,
  `test_pacto_command_says_it_is_working_before_the_picker_arrives`,
  `test_pact_callback_acknowledges_the_tap_with_a_toast`,
  `test_pact_callback_toggles_the_manager_and_redraws_in_place`,
  `test_pact_callback_ignores_a_malformed_manager_id`,
  `test_pacto_command_handles_a_fetch_failure`

---

### Requirement: Allowlisted chats get the public commands, and only those

The owner shares the league's cash with a league mate by hand, by
screenshots cropped to hide what concerns his own team. The bot SHALL do it
instead, for the chats the owner chooses, without opening anything else to
them.

A chat on the public allowlist SHALL be routed to a public handler that
answers `/saldos`, `/movimientos`, `/analizar`, `/mercado` and `/ayuda`. Any
other text
gets the short help. An allowlisted chat is either a mate's private chat (his
user id) or a group the owner opened with the bot and the mate, so he can
follow what the mate asks. A group counts only once its own id is on the list,
never because a member of it is. The admin commands, the reply-keyboard label
router, every admin callback prefix and the photo path SHALL be unreachable
from those chats, as they are from the draft group, and that includes the
owner's own messages inside such a group.

A chat that is neither the owner's, the draft group's nor on the allowlist
SHALL still get no reply. Answering strangers, even to say access is closed,
makes the bot something anyone can probe. It SHALL, though, be remembered,
with its title, for the owner to authorize from `/publico`. A group's id is
otherwise hard to find.

#### Scenario: an allowlisted chat reaches the public set only
- **WHEN** an allowlisted private chat sends `/saldos` or `/movimientos`
  **THEN** the matching public API call is made, answered to that chat
- **WHEN** a group the owner added sends `/saldos@bot` **THEN** it is answered
  in that group
- **WHEN** it sends an admin command (`/alinear`, `/ofertas`, `/analizar` …)
  **THEN** the API is not called and the short help is sent
- **WHEN** it sends text matching a reply-keyboard label **THEN** the label
  router is not consulted
- **WHEN** it sends a callback with an admin prefix **THEN** it is refused
- **WHEN** it sends a photo **THEN** it is ignored
- *Verifies:* `test_allowlisted_member_saldos_calls_the_public_api`,
  `test_allowlisted_member_movimientos_calls_the_public_api`,
  `test_a_group_the_owner_added_gets_the_public_set`,
  `test_admin_command_from_a_public_member_gets_the_help_not_the_api`,
  `test_public_member_message_does_not_consult_label_dispatch`,
  `test_admin_callback_from_a_public_member_is_refused`,
  `test_photo_from_a_public_member_is_ignored`

#### Scenario: who is not let in
- **WHEN** a private chat not on the allowlist sends `/saldos` **THEN** it gets
  no reply and nothing reaches a public endpoint or Biwenger. The gate check
  is the only call, and it remembers the chat for `/publico`.
- **WHEN** a group not on the allowlist sends a public command **THEN** it is
  ignored the same way
- **WHEN** an id is removed from the allowlist **THEN** that chat is ignored
  from the next message on
- *Verifies:* `test_unlisted_private_chat_is_silently_ignored`,
  `test_an_unlisted_group_is_ignored`,
  `test_an_unknown_chat_is_offered_to_the_owner_without_a_reply`,
  `test_an_unknown_chat_is_remembered_for_the_owner_to_authorize`,
  `test_a_member_chat_passes_the_gate_and_is_not_remembered`,
  `test_a_removed_member_is_ignored_again`

#### Scenario: a failure says little
- **WHEN** the public API call fails **THEN** the member reads "no disponible
  ahora", with no exception text
- *Verifies:* `test_public_failure_hides_the_exception`

### Requirement: The public `/analizar` shows the rivals, never the owner

`/analizar` from a public chat SHALL offer a picker of every manager but the
owner, and a tap SHALL send that rival's squad image to the chat that asked:
the blended projection, the clause columns and the fixtures, as the owner's
own `/analizar` draws a rival. The owner's squad SHALL never be offered, and
the api SHALL refuse it even when asked for by id. It is his information about
his own team. There is no "TODOS" and no market.

Each rival's image and the picker's list SHALL go through the public cache.
A fresh image costs a JP and Oráculo read plus about ten Biwenger requests
from the owner's account, and the button invites repeated taps. A cache write
that fails SHALL still answer.

Only the `pa:<manager_id>` callback SHALL be read from a public chat, and
only after the gate. Every other callback from such a chat stays ignored.

#### Scenario: rivals only, cached, gated
- **WHEN** a public chat sends `/analizar` **THEN** the picker lists the rivals
  and not the owner
- **WHEN** a rival is tapped **THEN** `/public/teams` is called for that chat and
  manager, through a cache keyed by manager
- **WHEN** the owner's id is asked for **THEN** nothing is read or sent
- **WHEN** the tap comes from a chat not on the allowlist **THEN** it is ignored
- *Verifies:* `test_public_analizar_opens_a_rivals_picker`,
  `test_public_analizar_tap_calls_the_public_api`,
  `test_public_analizar_tap_from_an_unlisted_chat_is_ignored`,
  `test_public_analizar_lists_only_rivals`,
  `test_public_analizar_never_shows_the_owner_team`,
  `test_public_analizar_sends_a_rival_to_the_asking_chat_cached_per_manager`,
  `test_public_analizar_refuses_a_non_member`,
  `test_a_cache_write_failure_still_answers`

### Requirement: `/publico` edits the public allowlist

The owner SHALL add and remove the chats on the public allowlist from his own
chat, without a redeploy:

- **`/publico <id> [nombre]`** adds a chat id: a user's, or a group's, which
  starts with a minus.
- **`/publico` alone** lists the members. Each is named by the label the owner
  gave him, else by the manager he registered as in the draft (`/soy`), and
  each has a remove button. Below them come the chats that wrote without
  access, each with an authorize button.

Adding a group SHALL register the public command block for that group and
removing it SHALL clear it, since a group has no private-chat menu to fall
back on.

The list SHALL be stored by the api, like the pact. The bot holds no state of
its own, per the zero-logic bot rule. A malformed id SHALL be refused without
an API call. `/publico` SHALL be reachable only from the owner's chat. A
draft registry that cannot be read SHALL cost only the names.

#### Scenario: add, name, list, authorize, remove, reject junk
- **WHEN** the owner sends `/publico 123456` **THEN** the id is added and
  confirmed
- **WHEN** he sends `/publico 777 Manu` **THEN** it is added with that name
- **WHEN** he sends `/publico` **THEN** each member is named (the given label
  wins over the draft name), with one remove button each
- **WHEN** a chat wrote without access **THEN** the list offers it with an
  authorize button
- **WHEN** he authorizes a group **THEN** it is added and its menu gets the
  public block; removing a group clears its menu
- **WHEN** he taps remove **THEN** that id is removed and the list redrawn in
  place
- **WHEN** the id is not numeric **THEN** it is refused, with no API call
- **WHEN** `/publico` arrives from a public chat or the draft group **THEN** it
  is refused
- *Verifies:* `test_publico_adds_a_numeric_id`,
  `test_publico_adds_an_id_with_a_name`,
  `test_publico_lists_members_with_remove_buttons`,
  `test_publico_list_shows_each_member_by_name`,
  `test_public_members_are_named_from_the_draft_registry`,
  `test_a_name_given_by_hand_wins_over_the_draft`,
  `test_a_draft_registry_that_cannot_be_read_costs_only_the_names`,
  `test_publico_list_offers_unknown_chats_to_authorize`,
  `test_publico_authorize_tap_adds_the_chat_and_scopes_its_menu`,
  `test_removing_a_group_clears_its_menu`,
  `test_publico_remove_tap_redraws_in_place`,
  `test_publico_rejects_a_non_numeric_id`,
  `test_publico_is_owner_only`,
  `test_public_members_edit_passes_an_optional_name`

### Requirement: Each command block is offered only in its own chats

The bot serves three audiences, and the `/` menu SHALL offer each one only
its own block. An operation suggested in the wrong chat invites a tap that
the routing will refuse, and an admin command listed where a league mate can
read it gives away what the owner can do.

| Block | Chats |
|---|---|
| Public (`/saldos`, `/movimientos`, `/analizar`, `/mercado`, `/ayuda`) | private chats, and each group the owner authorizes |
| Draft (`/pick`, `/estado`, `/soy`, `/deshacer`, `/exportar`) | the draft group |
| Base and management (everything else, `/publico` included, no draft command) | the owner's chat |
| None | any other group |

The post-deploy hook SHALL register them by Telegram scope, which picks the
narrowest match for each chat. It SHALL refuse to run without the owner's
chat id rather than fall back to a global list, since that fallback is
exactly the leak the blocks exist to prevent. The menu only suggests: the
webhook routing is what refuses a command outside its chat.

#### Scenario: each block in its own chats
- **WHEN** the hook runs **THEN** the default scope gets no commands, private
  chats get the public block, the owner's chat gets the base and management
  block and the draft group gets the draft block
- **WHEN** the owner's chat id is missing **THEN** it stops before
  registering anything
- **WHEN** the two lists are compared **THEN** the owner's block holds no
  draft command
- *Verifies:* `test_setup_scopes_each_block_to_its_chats`,
  `test_setup_refuses_to_publish_without_the_owner_chat`,
  `test_the_owner_block_holds_no_draft_command`
