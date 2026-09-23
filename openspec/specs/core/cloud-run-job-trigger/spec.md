# Capability: cloud-run-job-trigger

Starts a Cloud Run Job on demand. This is how the bot and the web admin panel
run the league scraper outside its schedule.

- **Source:** `core/sdk/gcp.py` (`trigger_cloud_run_job`)
- **Verified by:** no test covers it directly.

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

> **GAP — unverified.** No test covers the request or its errors. A test would
> patch `google.auth.default`, mock the `:run` URL, and assert the bearer
> header, the returned short name and a raise on 403. Candidate for the next
> test-hardening pass.
