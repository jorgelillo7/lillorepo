# biwenger_api

Cloud Run **Service** that exposes the Biwenger business logic over HTTP.
Called by the Telegram bot (synchronous, low-latency) and by Cloud Scheduler
(daily digest). Replaces the previous `teams_analyzer` Cloud Run **Job**, which
was being used as a service and paid a 5–10 s cold start on every `/alinear`.

## Status

PR 1 — **skeleton only**. Two endpoints:

- `GET /healthz` — liveness, returns `{"status": "ok"}`.
- `GET /version` — `{"service": "biwenger-api", "commit": ..., "deploy_time": ...}`.

Business-logic endpoints land in later PRs as we move modes out of
`teams_analyzer`. See `.claude/plans/biwenger_api_refactor.md`.

## Local dev

```bash
bazel run //packages/biwenger_tools/api:api_local
```

Then:

```bash
curl localhost:8080/healthz
curl localhost:8080/version
```

## Tests

```bash
bazel test //packages/biwenger_tools/api:api_tests --test_output=streamed --test_arg=-v
```

## Deploy

Pushed automatically by `.github/workflows/deploy.yml` on changes to this
directory, to `core/`, `tools/`, `docker/`, or `MODULE.bazel`.

Cloud Run service name: `biwenger-api`. Deployed with
`--no-allow-unauthenticated` — invokers (bot, scheduler) authenticate with a
Google-signed ID token whose `roles/run.invoker` binding is granted to their
service account.
