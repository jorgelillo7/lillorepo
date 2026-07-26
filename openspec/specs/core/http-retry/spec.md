# Capability: http-retry

The shared HTTP retry helper every SDK uses to survive transient upstream
failures without retrying unrecoverable ones.

- **Source:** `core/sdk/http.py` (`retry_http_request`)
- **Verified by:** `core/tests/test_http_retry.py`

---

### Requirement: Retry only what can recover

`retry_http_request(fn, label, backoffs)` SHALL return immediately on the first
success, raise immediately on a 4xx (caller error — retrying never helps), and
retry on 5xx or network errors, sleeping per the `backoffs` tuple. Total
attempts SHALL be `1 + len(backoffs)`; when they exhaust, the last error SHALL
be raised.

#### Scenario: success, fail-fast, retry, exhaust
- **WHEN** the call succeeds first try **THEN** it returns, no retry
- **WHEN** it returns 4xx **THEN** it raises immediately (one call)
- **WHEN** it returns 5xx or a network error then succeeds **THEN** it retries
  and returns
- **WHEN** 5xx / network errors persist **THEN** it raises after `1 + len(backoffs)`
  attempts
- *Verifies:* `test_returns_immediately_on_first_success`,
  `test_fail_fast_on_4xx_without_retrying`, `test_retries_on_5xx_then_succeeds`,
  `test_retries_on_network_error_then_succeeds`,
  `test_raises_after_exhausted_retries_on_persistent_5xx`,
  `test_raises_after_exhausted_retries_on_persistent_network_error`

### Requirement: Per-operation log label

Retries SHALL log the caller-supplied `label`, so Cloud Logging is searchable
per operation.

#### Scenario: label in logs
- **WHEN** a retryable failure is logged with `label="lineup PUT"`
- **THEN** the log record contains "lineup PUT"
- *Verifies:* `test_label_appears_in_logs`
