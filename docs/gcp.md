# GCP — services and cost decisions

Project: `biwenger-tools` · Region: `europe-southwest1` (Madrid)

## Services in use

| Service | Resource | Purpose |
|---|---|---|
| Cloud Run (Services) | `biwenger-summary` | Flask web app — comunicados, salseo, mercado, lloros awards |
| Cloud Run (Services) | `biwenger-api` | Biwenger business logic over HTTP (`--no-allow-unauthenticated`) |
| Cloud Run (Services) | `biwenger-bot` | Telegram bot — receives webhooks, calls `biwenger-api` |
| Cloud Run (Services) | `chucknorris-bot` | Chuck Norris jokes Telegram bot |
| Cloud Run (Jobs) | `biwenger-scraper-data` | Scrapes league messages → CSV → Google Drive |
| Cloud Scheduler | `biwenger-scraper-data-scheduler-trigger` (`europe-west1`) | Triggers scraper job (cron weekly Sun 22:00) |
| Cloud Scheduler | `biwenger-teams-analyzer-trigger` (`europe-west1`) | Triggers `biwenger-api/digests/daily` (daily 16:00 Madrid); name is legacy — points at the api now |
| Secret Manager | 4 secrets (see below) | Credentials and bot tokens |
| Artifact Registry | `biwenger-docker` | Docker images for all Cloud Run services/jobs |
| Cloud Logging | — | Automatic, structured logs via `get_logger()` |

## Secrets

| Secret | Contents |
|---|---|
| `biwenger-credentials-regional` | `{"email", "password", "gdrive_folder_id", "jp_auth_token"}` |
| `telegram-bot-config-regional` | `{"bot_token", "chat_id", "webhook_secret"}` |
| `chucknorris-bot-config-regional` | `{"bot_token", "webhook_secret"}` |
| `biwenger-tools-sa-regional` | Google Drive service account JSON key |

All secrets are regional (`europe-southwest1`). See "Cost decisions" below.

## Cost decisions

### Regional secrets, not global
Secret Manager charges per active version (first 6 free/month). Global replication
adds a replica per region you use, counting as extra versions. Using
`--replication-policy=user-managed --locations=europe-southwest1` keeps each secret
at exactly 1 active version.

### JSON secrets — one secret, multiple values
Consolidating related credentials into a single JSON secret (e.g., `biwenger-credentials-regional`
instead of separate `biwenger-email`, `biwenger-password`, `gdrive-folder-id`) reduces
active secret count from 9 to 4, staying well within the free tier.
Config modules read the JSON first, fall back to individual env vars for local dev.

The `jp_auth_token` (Jornada Perfecta) was added to `biwenger-credentials-regional` in
2026-05-16 instead of creating a new secret — same scope (now `biwenger-api`), no extra cost.

### Shared Python base image
All Cloud Run services and jobs extend a shared `python-base` image stored in Artifact Registry.
This is rebuilt only when dependencies change, not on every deploy. Benefits:
- Cold start time drops significantly (heavy deps like `google-cloud-*` are pre-installed).
- Artifact Registry storage stays low — only incremental layers change per deploy.

The image is **runtime-only**: test/dev deps (pytest, black, flake8, freezegun,
requests-mock and their transitives) are listed in `requirements_lock.txt` for
Bazel's hermetic sandbox but **not installed** in `Dockerfile.base`. Same for
the `googleapiclient/discovery_cache/documents` cache, which is pruned in the
same `RUN` layer to drive/sheets/run only — the 581 other JSON discovery docs
are dead weight (~96 MB). These two together drop the image from ~443 MB to
~275 MB, well inside the 500 MB Artifact Registry free tier.

When using \`pip install\` in the Dockerfile, keep \`--no-compile\` and the
\`__pycache__\` / \`.pyc\` cleanup at the end of the same \`RUN\` — Python
re-creates bytecode on first import, no need to ship it.

### min-instances = 0 on all services
No idle compute billing. All services are request-driven or job-driven.
Acceptable because this is a private league intranet, not a latency-sensitive product.

### Bots with cpu=0.5 + concurrency=1
`biwenger-bot` and `chucknorris-bot` are webhook handlers that do at most one
HTTP call per request (call to `biwenger-api`, or fetch from chucknorris.io).
They serve one request per instance and scale horizontally if a second arrives
in flight. GCP forbids `cpu < 1` with `concurrency > 1`, so this is the
configuration that buys the cpu reduction. The web and api services stay at
`cpu=1` — they do the heavy work (templates, matplotlib, Biwenger/JP traffic).

### Log retention 7 days
The `_Default` log bucket retains for 7 days (down from the GCP default of 30). At our
volume we stay far below the 50 GB/month free ingestion, but a shorter retention caps
the long-tail storage cost as the project grows and gives us a smaller window when
debugging — by design, recent issues are the only ones worth debugging.

### Budget alert at €1/month
A budget named "€1 Alerta de presupuesto mensual" fires email alerts at 50%, 90%,
100% and 150% of €1 EUR. €1 is a meaningful threshold given we should be on the
free tier; any breach is a signal that something has escaped the constraints, not a
normal-operations event.

### Artifact Registry cleanup includes every service
`scripts/clean-images-artifact.sh` purges old digests per image. Note that the
`SIMPLE_IMAGES` array must list **every** Cloud Run service/job repo — `chucknorris_bot`
was missing until 2026-05-16 and quietly accumulated 8 digests. When adding a new
service, add its repo name to that array. `python-base` is multi-arch and managed
separately (deletes only orphan untagged digests older than 24 h).

The script is invoked by CI's `cleanup` job after any successful deploy. If a week
passes without merges, run it manually.

### Cloud Run instead of GCE/GKE
Serverless — no VM management, no always-on cost. Free tier: 2M requests/month,
360k vCPU-seconds, 180k GiB-seconds (shared across all services and jobs).

### europe-southwest1 (Madrid)
Chosen for latency to users (all Spanish), not for cost. Pricing is equivalent to
other European regions.

## Cost monitoring

```bash
bash scripts/check-gcp-costs.sh
```

Covers: Cloud Storage, Artifact Registry, Cloud Run services/jobs, Secret Manager,
Cloud Scheduler, Cloud Logging. Shows free-tier usage % and OK/WARN/OVER status.
For Cloud Build and Monitoring billing, check Cloud Console > Billing.
