# GCP — services and cost decisions

Project: `biwenger-tools` · Region: `europe-southwest1` (Madrid)

> **Cross-project inventory** (all projects, all regions, at a glance):
> [`INFRA.md`](../INFRA.md) at the repo root. This document keeps the
> biwenger-specific detail and the *rationale* behind each choice.

## Services in use

| Service | Resource | Purpose |
|---|---|---|
| Cloud Run (Services) | `biwenger-summary` | Flask web app — comunicados, salseo, mercado, competiciones |
| Cloud Run (Services) | `biwenger-api` | Biwenger business logic over HTTP (private: no `allUsers` invoker) |
| Cloud Run (Services) | `biwenger-bot` | Telegram bot — receives webhooks, calls `biwenger-api` |
| Cloud Run (Services) | `chucknorris-bot` | Chuck Norris jokes Telegram bot |
| Cloud Run (Jobs) | `biwenger-scraper-data` | Scrapes the league board → Firestore (`comunicados`, `participacion`, `clausulazos`, `tabla_justicia`, `board_archive`) |
| Cloud Scheduler | `biwenger-scraper-data-scheduler-trigger` (`europe-west1`) | Triggers scraper job (cron weekly Sun 22:00) |
| Cloud Scheduler | `biwenger-daily-digest-trigger` (`europe-west1`) | Triggers `biwenger-api/digests/daily` (daily 09:00 Madrid) — sends squad + market images and chains the auto-bid summary at the end |
| Secret Manager | 3 secrets, one per package (see below) | Credentials and bot tokens |
| Artifact Registry | `biwenger-docker` | Docker images for all Cloud Run services/jobs |
| Cloud Logging | — | Automatic, structured logs via `get_logger()` |

## Secrets

| Secret | Contents | Mounted by |
|---|---|---|
| `biwenger-secrets` | `{"email", "password", "jp_auth_token", "bot_token", "chat_id", "draft_chat_id", "draft_admin_telegram_id", "webhook_secret", "secret_key", "admin_password"}` | api and scraper (`BIWENGER_CREDENTIALS_JSON` + `TELEGRAM_BOT_CONFIG_JSON`), bot (`TELEGRAM_BOT_CONFIG_JSON`), web (`FLASK_WEB_CONFIG_JSON`) |
| `chucknorris-secrets` | `{"bot_token", "webhook_secret"}` | chucknorris-bot |
| `be-water-secrets` (project `be-water-app`) | `{"secret_key", "gemini_api_key", "gemini_api_key_paid", "telegram_bot_token", "telegram_chat_id"}` | be-water |

All secrets are regional (`europe-southwest1`). See "Cost decisions" below.

### No key files — do NOT set `GOOGLE_APPLICATION_CREDENTIALS`

Every Google client runs on ADC: in Cloud Run that is the service's own
account (below), locally the developer's `gcloud auth application-default login`.
The web reads the competitions workbooks the same way — the "Biwenger" Drive
folder holding them is shared, as Viewer, with
`run-biwenger-web@biwenger-tools.iam.gserviceaccount.com` — so no
service-account key exists anywhere. Locally, the competitions tab
needs ADC with the Sheets scope:

```bash
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/spreadsheets.readonly
```

Never set `GOOGLE_APPLICATION_CREDENTIALS` in `BUILD.bazel` or a deploy: the
Firestore client honours it automatically, and a path that does not exist in
the image crashed every Firestore read once.

### Runtime identities — one service account per service

No service runs as the default compute account, which carries `roles/editor`
on the whole project. Each has only what it touches; grants sit on the
resource (secret, bucket, service, job) wherever IAM allows it.

| Runs as | Service | Holds |
|---|---|---|
| `run-biwenger-api` | `biwenger-api` | Firestore read/write · `biwenger-secrets` · `storage.objectUser` on `gs://biwenger` · run the scraper job |
| `run-biwenger-bot` | `biwenger-bot` | `biwenger-secrets` · invoke `biwenger-api` |
| `run-biwenger-web` | `biwenger-summary` | Firestore **read** · `biwenger-secrets` · run the scraper job · the Drive folder (Viewer) |
| `run-biwenger-scraper` | job `biwenger-scraper-data` | Firestore read/write · `biwenger-secrets` |
| `run-chucknorris-bot` | `chucknorris-bot` | `chucknorris-secrets` |
| `scheduler-invoker` | both Cloud Scheduler jobs | invoke `biwenger-api` · run the scraper job |
| `run-be-water` (`be-water-app`) | `be-water` | Firestore read/write · `storage.objectUser` on `gs://be-water-photos` · `be-water-secrets` |

`deploy.yml` passes `--service-account` on every deploy, and CI's own account
holds `iam.serviceAccountUser` on each. A new service gets its own account the
same way (`DEPLOY_YOUR_OWN.md`, step 7) — never the compute default.

### Content-Security-Policy on both webs

Each web declares, per page, where scripts, styles, fonts, images and frames may
come from (`CSP` in its `app.py`, applied by `core.web.headers`). It is the
second line against XSS: if HTML ever slipped past the sanitiser, the browser
would still refuse to run it.

- **Scripts run only with the request's nonce.** Every `<script>` carries
  `nonce="{{ csp_nonce() }}"`; one without it does not run. That is why the
  templates have no `onclick=`-style attributes — a nonce cannot cover them.
  Handlers are `data-on-click="fn"` (+ `data-args` as JSON, `"@this"` for the
  element), dispatched by one script in `base.html`; `data-confirm` replaces
  `onsubmit="return confirm(...)"`. JSON-LD blocks need no nonce: they are
  data, not code.
- **Styles keep `'unsafe-inline'`.** Tailwind's CDN build generates them in the
  browser. Moving to a Tailwind build step (parked in `PENDING.md`) is what
  would let them go.
- **Violations are reported.** The browser posts what it blocks to
  `/csp-report`, logged as a `WARNING` (`CSP blocked a source.`, with the URL,
  directive and page). A new external source — a font, an embed, an image
  host — must be added to that web's `CSP`, or it is blocked and shows up
  there.

Verified in headless Chrome over every page of both webs: no violation, every
handler reaches its function, and an injected script without the nonce is
blocked and reported.

### Who may call each service is set once, not by CI

Public services carry `allUsers` as `roles/run.invoker`; `biwenger-api` does
not, and only its callers' service accounts hold the role. That binding is set
when a service is created (`DEPLOY_YOUR_OWN.md` does it) and CI never touches
it: `deploy.yml` passes no `--allow-unauthenticated`, because its service
account (`run.developer`) may not change IAM — the flag only produced a
`run.services.setIamPolicy` denial on every deploy. To change who can call a
service, use `gcloud run services add-iam-policy-binding` by hand.

## Cost decisions

### Regional secrets, not global
Secret Manager charges per active version — the first 6 free/month are counted
**per billing account, not per project** (learned 2026-07-18: biwenger's 5 +
be-water's 1 leave the account at exactly 6/6). Global replication adds a
replica per region you use, counting as extra versions. Using
`--replication-policy=user-managed --locations=europe-southwest1` keeps each
secret at exactly 1 active version. Before creating a 7th version anywhere on
the account, consolidate (see the JSON-secret pattern below).

**Disabled versions still bill** — only *destroyed* ones don't. Adding a new
secret version and disabling the old one keeps paying $0.06/month for it.
This produced the project's first-ever charge (July 2026: 5 stale disabled
versions from the initial setup → 9 billable versions > 6 free). After
verifying a new version works, destroy the old one:
`gcloud secrets versions destroy <v> --secret=<name>`.
`scripts/check-gcp-costs.sh` counts billable versions and flags disabled ones.

### One secret per package
Every package keeps its credentials in a single JSON secret, and a service
mounts it under the env var names its config already reads — the keys do not
collide, and each config picks only its own. That keeps the billing account
at **3 of its 6 free versions** (it sat at 6/6 before), with no Google key
file anywhere: the web reads Sheets as its Cloud Run identity.

The accepted cost is least privilege: `biwenger-bot` and the web, the two
public biwenger services, can read the Biwenger password and the JP token they
never use. Accepted for a private league with one operator — see `STATUS.md`.
Rotating any value means redeploying every service that mounts the secret.

### Shared Python base image
All Cloud Run services and jobs extend a shared `python-base` image stored in Artifact Registry.
This is rebuilt only when dependencies change, not on every deploy. Benefits:
- Cold start time drops significantly (heavy deps like `google-cloud-*` are pre-installed).
- Artifact Registry storage stays low — only incremental layers change per deploy.

The image is **runtime-only**: test/dev deps (pytest, ruff, freezegun,
requests-mock and their transitives) are listed in `requirements_lock.txt` for
Bazel's hermetic sandbox but **not installed** in `Dockerfile.base`. Same for
the `googleapiclient/discovery_cache/documents` cache, which is pruned in the
same `RUN` layer to drive/sheets/run only — the 581 other JSON discovery docs
are dead weight (~96 MB). These two together drop the image from ~443 MB to
~275 MB, well inside the 500 MB Artifact Registry free tier.

### linux/amd64 only, with bytecode compiled in

The base is built for **linux/amd64 only** — what Cloud Run runs. A second
architecture (arm64) only served running production images in Docker on a Mac,
and doubled the base in the registry. With it gone, the base carries
**precompiled bytecode** instead: `compileall` runs last in the install `RUN`,
after the `.pyc` sweep. Measured on amd64: `matplotlib.pyplot` imports in 0.8 s
instead of 2.6 s, Firestore 0.5 s instead of 1.7 s, Flask 0.4 s instead of 1.0 s
— every cold start used to pay that. Net registry cost: the base went from
204 MB (two architectures) to 127 MB compressed. Reversing this was reasoned in
the PR that did it; the free tier, not taste, is what to re-check first.

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
service, add its repo name to that array. `python-base` is an image index (the amd64 image plus its build
attestation) and is managed separately (deletes only orphan untagged digests older than 24 h).

The script is invoked by CI's `cleanup` job after any successful deploy. If a week
passes without merges, run it manually.

### Cloud Run instead of GCE/GKE
Serverless — no VM management, no always-on cost. Free tier: 2M requests/month,
360k vCPU-seconds, 180k GiB-seconds (shared across all services and jobs).

### europe-southwest1 (Madrid) — single-region policy
Chosen for latency to users (all Spanish), not for cost. Pricing is equivalent to
other European regions. Everything that *can* live in Madrid *does*:

| Resource | Region |
|---|---|
| Cloud Run services + job | `europe-southwest1` |
| Firestore (default) | `europe-southwest1` |
| Artifact Registry (`biwenger-docker`) | `europe-southwest1` |
| Secrets (user-managed replication) | `europe-southwest1` |
| Cloud Scheduler (both triggers) | `europe-west1` — **deliberate, see below** |

**Cloud Scheduler is not offered in `europe-southwest1`** (check
`gcloud scheduler locations list`), so the two cron triggers live in
`europe-west1` (Belgium), the closest supported region. Impact is nil: a
scheduler job stores no data (just cron config + target URL), pricing is
per-job regardless of region (3 free per billing account), and the
cross-region HTTPS tick adds ~10 ms to a 5-minute SLO. Do not try to
migrate them to Madrid — the API will reject the location.

## Cross-project deploys (`be-water-app`)

be_water lives in its own GCP project but deploys from this repo's single CI
pipeline using the shared WIF service account
(`biwenger-tools-sa@biwenger-tools.iam.gserviceaccount.com`). Grants on
`be-water-app`:

| Grant | Scope | Why |
|---|---|---|
| `roles/run.admin` | project | `gcloud run deploy be-water` |
| `roles/artifactregistry.writer` | project | push the `web` image to `be-water-docker` |
| `roles/artifactregistry.repoAdmin` | repo `be-water-docker` | the CI cleanup job deletes old digests (writer can push but not delete) |
| `roles/iam.serviceAccountUser` | `run-be-water` | `actAs` required by `gcloud run deploy` |

## Cost monitoring

```bash
bash scripts/check-gcp-costs.sh                       # both projects + account-wide secrets
bash scripts/check-gcp-costs.sh --project=be-water-app  # single project
```

Covers: Cloud Storage (with per-bucket free-tier eligibility — the always-free
5 GB only exists in US regions), Artifact Registry, Cloud Run services/jobs,
Firestore, Secret Manager and Artifact Registry (per-project detail + billing-account total — both free tiers are per account, not per project),
Cloud Scheduler, Cloud Logging, budgets, log retention and Cloud Run config
drift. Shows free-tier usage % and OK/WARN/OVER status.
For Cloud Build and Monitoring billing, check Cloud Console > Billing.
