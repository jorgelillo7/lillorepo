# Capability: chuck-jokes

A Telegram bot that serves Chuck Norris jokes (random or by category) via a
secured webhook and a persistent reply keyboard.

- **Source:** `packages/chucknorris_bot/bot/app.py`
- **Verified by:** `packages/chucknorris_bot/bot/tests/test_app.py`

---

### Requirement: Webhook is secret-gated

The webhook SHALL reject requests without the correct
`X-Telegram-Bot-Api-Secret-Token` (401) and accept correct ones (200).

#### Scenario: secret enforcement
- **WHEN** the secret is wrong **THEN** 401
- **WHEN** it is correct **THEN** 200
- *Verifies:* `test_wrong_secret_returns_401`, `test_correct_secret_returns_200`

### Requirement: Help/start show the persistent keyboard

`/help` and `/start` SHALL send the welcome text plus a persistent reply
keyboard exposing the fact categories (🎲 Random, 💻 Dev, …).

#### Scenario: keyboard attached
- **WHEN** `/help` or `/start` is received
- **THEN** the reply carries `is_persistent: true` and the category buttons
- *Verifies:* `test_help_attaches_persistent_reply_keyboard`,
  `test_start_attaches_persistent_reply_keyboard`

### Requirement: Jokes by command and by keyboard label

Both slash commands (`/random`, `/science`, `/food`, `/animal`, `/dev`) and the
keyboard labels SHALL fetch a joke — random with no category, or the mapped
category — and reply with the text. `/version` SHALL return the commit + deploy
time injected by CI. Unknown commands, messages without text, and empty bodies
SHALL be ignored (200, no send). A `@botname` suffix SHALL still be parsed.

#### Scenario: dispatch, version, and ignored inputs
- **WHEN** a command or keyboard label maps to a category **THEN** `_fetch_joke`
  is called with that category (or `None` for random) and the joke is sent
- **WHEN** `/version` **THEN** the commit + deploy time are returned
- **WHEN** the input is unknown / has no text / is an empty body
- **THEN** it is ignored with no send
- *Verifies:* `test_reply_keyboard_label_dispatches_joke`, `test_random_fetches_and_sends`,
  `test_category_command_fetches_with_category`, `test_version_returns_commit_and_deploy_time`,
  `test_unknown_command_is_ignored`, `test_message_without_text_is_ignored`,
  `test_empty_body_does_not_crash`, `test_command_with_botname_suffix_is_parsed`

### Requirement: Joke fetch degrades gracefully

`_fetch_joke` SHALL call the jokes API (appending `category=` when given) and,
on any error, return a safe fallback line rather than propagating.

#### Scenario: fetch, category param, error fallback
- **WHEN** the API returns a joke **THEN** its value is returned
- **WHEN** a category is given **THEN** the request carries `category=<cat>`
- **WHEN** the request raises **THEN** a Chuck-Norris fallback string is returned
- *Verifies:* `test_fetch_joke_returns_joke`, `test_fetch_joke_with_category_appends_param`,
  `test_fetch_joke_handles_error`
