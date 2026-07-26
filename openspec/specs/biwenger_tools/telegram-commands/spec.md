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
suffix), `/preview` SHALL call auto-pick with `?dry_run=1`, and an API failure
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
tell the user when the managers list is unreachable.

#### Scenario: keyboard and picker
- **WHEN** `/menu` or `/start` **THEN** the persistent keyboard is sent
- **WHEN** a keyboard label is tapped **THEN** the mapped action fires
- **WHEN** `/analizar` **THEN** a manager picker opens; a manager tap calls
  `/teams?manager=<id>`, the TODOS tap calls `/teams` with no filter
- **WHEN** the managers fetch fails **THEN** the user is told
- *Verifies:* `test_menu_sends_persistent_reply_keyboard`, `test_start_aliases_menu`,
  `test_reply_keyboard_label_dispatches_action`,
  `test_reply_keyboard_analizar_label_opens_picker`,
  `test_analizar_text_command_opens_manager_picker`,
  `test_analizar_text_command_handles_manager_fetch_failure`,
  `test_analizar_id_callback_calls_teams_with_filter`,
  `test_analizar_all_callback_calls_teams_without_filter`

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
