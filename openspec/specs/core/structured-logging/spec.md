# Capability: structured-logging

The logger every module uses (`get_logger`), writing one JSON object per line
to stdout for Cloud Logging to index.

- **Source:** `core/utils.py` (`get_logger`), `core/serving/gunicorn_conf.py`,
  `core/web/logs.py` (`use_json_logging`)
- **Verified by:** `core/tests/test_utils.py`, `core/tests/test_serving_gunicorn.py`,
  `core/tests/test_web_logging.py`

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

### Requirement: gunicorn's own lines are graded too

gunicorn's error log (boot, worker timeouts, crashes) SHALL go through the
same JSON formatter, so a worker timeout reaches Cloud Logging as CRITICAL.
gunicorn's access log SHALL stay off — Cloud Run already writes a request
log — and gunicorn's configuration SHALL add no handler to the root logger,
which would print every application line twice.

#### Scenario: worker timeout, no access lines, no duplicates
- **WHEN** gunicorn logs `WORKER TIMEOUT` at CRITICAL **THEN** it is one JSON
  line with `severity="CRITICAL"`
- **WHEN** a request is served **THEN** no access line is written
- **WHEN** an application logger writes after gunicorn configured logging
  **THEN** the line is not repeated on stdout
- *Verifies:* `test_gunicorn_lines_are_json_with_severity`,
  `test_gunicorn_access_lines_stay_off`, `test_gunicorn_config_adds_no_root_handler`

### Requirement: an unhandled Flask exception is one ERROR entry

Every Flask app SHALL replace Flask's default handler with the JSON one, so an
unhandled exception is a single `severity="ERROR"` line carrying the traceback
in `exc_info`, rather than raw text Cloud Logging splits into many entries.

#### Scenario: a route raises
- **WHEN** a route raises and Flask answers 500
- **THEN** exactly one JSON line is written, `severity="ERROR"`, with the
  exception in `exc_info`
- *Verifies:* `test_an_unhandled_exception_is_one_json_error_line`,
  `test_the_default_flask_handler_is_gone`
