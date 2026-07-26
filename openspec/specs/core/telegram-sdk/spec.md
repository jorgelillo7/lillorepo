# Capability: telegram-sdk

Shared Telegram helpers every bot/service uses: message delivery, command
parsing, and webhook validation/extraction.

- **Source:** `core/sdk/telegram.py`
- **Verified by:** `core/tests/test_telegram_notifier.py`

---

### Requirement: Message delivery

`send_telegram_message` SHALL POST with `parse_mode=HTML` and web-page preview
disabled, truncate text to Telegram's 4096-char limit (ending in "..."), return
`True` on success and `False` on a 4xx/5xx (logging the failure) so callers can
choose to swallow or re-raise. (A raising variant, `send_telegram_message_or_raise`,
exists for callers that must surface delivery failures — see auto-bid /
daily-digest specs.)

#### Scenario: success, truncation, failure signal
- **WHEN** a message is sent **THEN** it posts as HTML, preview disabled, returns True
- **WHEN** the text exceeds 4096 chars **THEN** it is truncated to 4096 ending "..."
- **WHEN** the API returns 4xx/5xx **THEN** it returns False and logs the failure
- *Verifies:* `test_send_telegram_message_success`,
  `test_send_telegram_message_truncates_long_text`,
  `test_send_telegram_message_returns_false_and_logs_on_api_failure`

### Requirement: Command parsing

`parse_command` SHALL normalise a message into a bare command: strip the
`@botname` suffix, lowercase, strip arguments, and return `""` for empty or
whitespace-only input.

#### Scenario: normalisation cases
- **WHEN** the text is "/Random@mybot" / "/HELP" / "/cmd arg" / "" / "   "
- **THEN** "/random" / "/help" / "/cmd" / "" / ""
- *Verifies:* `test_parse_command_strips_botname`, `test_parse_command_lowercases`,
  `test_parse_command_strips_arguments`, `test_parse_command_empty_string`,
  `test_parse_command_whitespace_only`

### Requirement: Webhook validation and extraction

`validate_webhook_secret` SHALL accept a matching secret header and reject a
mismatch or empty header. `extract_webhook_update` SHALL pull `(chat_id, text)`
from a normal update, stripping text whitespace, and handle an empty body or a
missing text key without crashing.

#### Scenario: secret and update extraction
- **WHEN** the secret header matches / mismatches / is empty
- **THEN** validation passes / fails / fails
- **WHEN** the update is normal / empty / has whitespace / has no text key
- **THEN** it extracts / degrades safely (no crash), stripping whitespace
- *Verifies:* `test_validate_webhook_secret_match`,
  `test_validate_webhook_secret_mismatch`, `test_validate_webhook_secret_empty_header`,
  `test_extract_webhook_update_normal`, `test_extract_webhook_update_empty_body`,
  `test_extract_webhook_update_strips_text_whitespace`,
  `test_extract_webhook_update_no_text_key`
