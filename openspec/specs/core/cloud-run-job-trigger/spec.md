# Capability: cloud-run-job-trigger

Starts a Cloud Run Job on demand. This is how the bot and the web admin panel
run the league scraper outside its schedule.

- **Source:** `core/sdk/gcp.py` (`trigger_cloud_run_job`)
- **Verified by:** `core/tests/test_gcp_services.py`

---

### Requirement: One authenticated call, the execution name back

`trigger_cloud_run_job(project, region, job_name)` SHALL call the Cloud Run
Admin API's `jobs/{job}:run` with an ADC bearer token and return the short
execution name. It SHALL raise `requests.HTTPError` on a non-2xx response and
`GoogleAuthError` when credentials cannot be obtained.

ADC means the runtime service account only needs `run.executions.create`, with
no key file to mount. The caller shows the execution name to the user so the
run can be found in the console. A failed trigger has to reach whoever asked
for it, not disappear.

#### Scenario: execution name, and a refused trigger
- **WHEN** the job starts **THEN** the request carries the ADC bearer token and
  the short execution name is returned
- **WHEN** the API answers 403 **THEN** `requests.HTTPError` is raised
- *Verifies:* `test_trigger_cloud_run_job_returns_the_short_execution_name`,
  `test_trigger_cloud_run_job_raises_when_denied`
