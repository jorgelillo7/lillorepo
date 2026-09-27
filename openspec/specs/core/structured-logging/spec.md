# Capability: structured-logging

The logger every module uses (`get_logger`), writing one JSON object per line
to stdout for Cloud Logging to index.

- **Source:** `core/utils.py` (`get_logger`)
- **Verified by:** `core/tests/test_utils.py`

---

### Requirement: Severity Cloud Logging understands

Each line SHALL carry a `severity` field equal to the record's level name
(`INFO`, `WARNING`, `ERROR`, `CRITICAL`), so Cloud Logging files the entry at
that severity rather than `DEFAULT`, and a `severity>=ERROR` filter finds
application errors.

#### Scenario: every level maps to its severity
- **WHEN** a module logs at INFO, WARNING, ERROR or CRITICAL
- **THEN** the JSON line's `severity` is that level's name
- *Verifies:* `test_log_lines_carry_cloud_logging_severity`

### Requirement: Existing fields stay

Each line SHALL keep `levelname`, `message` and every `extra` key as top-level
fields, so queries written against them (`jsonPayload.levelname`,
`jsonPayload.chat_id`) keep working.

#### Scenario: fields survive alongside severity
- **WHEN** an error is logged with `extra={"chat_id": 42}`
- **THEN** the line has `levelname="ERROR"`, the message, and `chat_id=42`
- *Verifies:* `test_log_lines_keep_levelname_message_and_extra`
