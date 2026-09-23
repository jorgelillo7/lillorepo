# Capability: service-launcher

The single entry point every Cloud Run service in the repo uses to start
gunicorn.

- **Source:** `core/serving/gunicorn.py`
- **Verified by:** `core/tests/test_serving_gunicorn.py`

---

### Requirement: Port 8080, an optional longer timeout, app path last

`run(app_path, timeout=None)` SHALL start gunicorn bound to `0.0.0.0:8080`
serving `app_path`. When `timeout` is given it SHALL pass `--timeout` before
the app path. When it is not, gunicorn's own default SHALL apply.

Cloud Run routes to port 8080. A handler that legitimately runs longer than
gunicorn's 30 s default (chained external calls, heavy rendering, uploads) is
killed with SIGKILL before any `except` block runs. The caller then gets a
500 with no error message at all, so services with such handlers raise the
timeout explicitly. gunicorn reads its argv positionally, so the app path
must stay last.

#### Scenario: default, raised timeout, hand-off
- **WHEN** `run` is called without a timeout **THEN** argv binds 8080 and
  names only the app
- **WHEN** a timeout is given **THEN** `--timeout N` comes before the app path
- **WHEN** `run` is called **THEN** it hands off to gunicorn's own entry point
- *Verifies:* `test_run_without_timeout_omits_the_flag`,
  `test_run_with_timeout_adds_the_flag_before_the_app_path`,
  `test_run_invokes_gunicorns_own_entrypoint`
