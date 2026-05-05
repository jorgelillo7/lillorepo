# Next phases — pickup notes for a fresh session

Entry point for any session continuing after the JP rewrite (v4.2) and the
Phase A + deps deploy (PR #6, merged 2026-05-05). Reads in ~3 minutes.

## State on 2026-05-05

- **`master`**: clean. PR #6 merged (Phase A + all dep bumps).
- **PR #7 open** (`feat/telegram-webhook`): implements the Telegram webhook
  **but with a coupling that was decided to revert** — see Phase B below.
  **Do NOT merge PR #7 as-is.** Close it and implement Phase B fresh.
- **JP API**: alive, token unchanged, 546 players, Nico Williams SF=571 ✓.

## What shipped in PR #6

- `biwenger-teams-analyzer` Cloud Run Job created and running.
- Cloud Scheduler fires it daily at 16:00 Madrid.
- CI auto-deploys the analyzer on code changes (`deploy-teams-analyzer` job).
- Smoke test passed: 7 Telegram messages sent, exit(0).
- Bazel modules: `rules_python` 0.40→2.0, `platforms` 0.0.10→1.1 (no more
  per-build MVS warnings).
- GH Actions: all bumped (checkout v6, setup-python v6, setup-bazel 0.19,
  paths-filter v4, auth/setup-gcloud v3). `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`
  removed.
- Python libs: gunicorn 26, black 26, pytest 9, flask 3.1.3, google-auth 2.50,
  requests 2.33, etc. `python-base` image rebuilt and digest updated.
- `rules_oci` stayed at 2.3.0 — 2.3.1 not in BCR yet; revisit any future PR.

## Decisions already taken (don't reopen)

- **Telegram webhook lives in a dedicated service**, not in the web app.
  See Phase B below for the architecture.
- Telegram bot auto-lineup endpoint: Phase C. Blocked on multi-position research.
- Firestore migration: not started, domain models are ready.
- Chuck Norris bot: separate GCP project, separate repo, nothing to do with
  this monorepo.

---

## Phase B — Dedicated `biwenger-telegram-bot` service (~2-3h)

**Goal:** `/analizar` from Telegram triggers a fresh analysis without waiting
for the daily cron. Clean architecture: the web app stays pure UI, the
telegram bot is its own service.

**Why not in the web app?** The web and analyzer are independent services —
coupling them (as PR #7 did) makes both images heavier, risks the web worker
blocking on a 15s analyzer run, and ties deployment cycles together.

**Pre-req:** PR #7 must be closed (not merged). All Cloud Run Job + secrets
infrastructure is already in place from Phase A.

### Architecture

```
biwenger-tools (GCP project)
├── biwenger-summary          ← web Flask, visualisation only (unchanged)
├── biwenger-scraper-data     ← Cloud Run Job, scraping
├── biwenger-teams-analyzer   ← Cloud Run Job, daily analysis
└── biwenger-telegram-bot     ← NEW Cloud Run Service
                                 POST /telegram/webhook
                                 /analizar → triggers the Job via Cloud Run API
                                 /alinear  → (Phase C, future)
                                 /help     → static text
```

The webhook handler calls the Cloud Run Jobs API to execute
`biwenger-teams-analyzer` and returns 200 immediately (async). No in-process
import of analyzer code.

### Steps

1. **Close PR #7** — don't merge.

2. **New Bazel package** `packages/biwenger_tools/telegram_bot/`:
   - `telegram_bot.py` — Flask app, single blueprint `POST /telegram/webhook`
   - `config.py` — reads `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
     `TELEGRAM_WEBHOOK_SECRET`, `GCP_PROJECT_ID`, `CLOUD_RUN_REGION`,
     `CLOUD_RUN_JOB_NAME` from env.
   - `BUILD.bazel` — `python_service` macro (new Cloud Run Service), no dep on
     `teams_analyzer_lib`.
   - `entrypoint.sh` — same pattern as web and scraper.
   - `requirements.txt` — `flask`, `gunicorn`, `python-dotenv`, `google-auth`,
     `google-api-python-client` (for Cloud Run Jobs API call).
   - Tests covering: wrong secret → 401, wrong chat_id → 200 silent,
     `/analizar` → triggers job once, `/help` → message sent, unknown → ignored.

3. **Triggering the Job via API** — use the Cloud Run Jobs REST API:

   ```python
   import google.auth
   import google.auth.transport.requests
   import requests as http_requests

   def trigger_analyzer_job(project: str, region: str, job_name: str):
       creds, _ = google.auth.default(
           scopes=["https://www.googleapis.com/auth/cloud-platform"]
       )
       creds.refresh(google.auth.transport.requests.Request())
       url = (
           f"https://{region}-run.googleapis.com/apis/run.googleapis.com/v1"
           f"/namespaces/{project}/jobs/{job_name}:run"
       )
       resp = http_requests.post(
           url, headers={"Authorization": f"Bearer {creds.token}"}
       )
       resp.raise_for_status()
   ```

   The webhook calls this and immediately returns `"", 200`. The Job runs
   independently.

4. **Deploy new Cloud Run Service**:

   ```bash
   # Build and push image
   bazel run //packages/biwenger_tools/telegram_bot:push_image_to_gcp \
       --platforms=//platforms:linux_amd64

   # Create the service (first time)
   gcloud run deploy biwenger-telegram-bot \
       --image=europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/telegram_bot:latest \
       --region=europe-southwest1 \
       --project=biwenger-tools \
       --allow-unauthenticated \
       --memory=256Mi --cpu=1 \
       --set-secrets="TELEGRAM_BOT_TOKEN=telegram-bot-token-regional:latest,\
   TELEGRAM_CHAT_ID=telegram-chat-id-regional:latest,\
   TELEGRAM_WEBHOOK_SECRET=telegram-webhook-secret-regional:latest" \
       --set-env-vars="GCP_PROJECT_ID=biwenger-tools,CLOUD_RUN_REGION=europe-southwest1,CLOUD_RUN_JOB_NAME=biwenger-teams-analyzer"
   ```

5. **Wire CI** — add `deploy-telegram-bot` job to `deploy.yml` mirroring
   `deploy-scraper`.

6. **Register the webhook** (one-time, after deploy):

   ```bash
   TOKEN=$(gcloud secrets versions access latest \
       --secret=telegram-bot-token-regional --project=biwenger-tools)
   SECRET=$(gcloud secrets versions access latest \
       --secret=telegram-webhook-secret-regional --project=biwenger-tools)

   curl -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
        -d "url=https://<new-service-url>/telegram/webhook" \
        -d "secret_token=${SECRET}" \
        -d "allowed_updates=[\"message\"]"
   ```

7. **Undo web coupling from PR #7** — the following changes from PR #7 should
   NOT be in master (PR #7 is not merged, so nothing to revert). Just don't
   carry them forward:
   - `extra_layers` param in `python_service.bzl`
   - `deps`/`extra_layers` in `web/BUILD.bazel`
   - `teams_analyzer_lib` visibility in `teams_analyzer/BUILD.bazel`
   - `telegram.py` blueprint in `web/routes/`
   - Telegram config vars in `web/config.py`
   - Telegram secrets in web's `deploy.yml` deploy step

   The docs commit in PR #7 (`operations.md`) can be salvaged and updated
   with the new service URL once it's deployed.

### Done criteria

- `/analizar` from the correct Telegram chat triggers a new Cloud Run Job
  execution (visible in GCP logs).
- The web app has zero knowledge of Telegram or the analyzer.
- A code change in `packages/biwenger_tools/telegram_bot/**` auto-deploys via CI.

---

## Phase C — Auto-lineup `/alinear` (in telegram_bot service)

**Pre-req:** Phase B done. AND the multi-position research spike must be
completed first.

### ⚠️ Research spike required before any code

The Biwenger squad API returns each player's `position` as a single int
(1=GK, 2=DEF, 3=MID, 4=FWD). The UI shows some players with two positions.
Before writing any lineup code:

1. Inspect dev-tools network tab on the squad page in Biwenger's web. Look
   for any endpoint returning `positions: [2, 3]` or similar.
2. If found: document in `docs/technical/reverse-engineering/biwenger-api.md`
   and add a method to `BiwengerClient`.
3. If not found: maintain a manual override map `{player_id: [2, 3]}`.
4. Write the answer in `teams_analyzer_rewrite.md` § "FASE 3 → Pendiente de
   investigar" before closing the spike.

The rest of Phase C is documented in the original `teams_analyzer_rewrite.md`.
The `/alinear` handler goes in the same `telegram_bot` service as `/analizar`.

---

## Phase D — Dependency maintenance (independent, anytime)

| Status | Bump | Notes |
|--------|------|-------|
| ✅ Done | `rules_python` 0.40→2.0 | No more MVS warning |
| ✅ Done | `platforms` 0.0.10→1.1 | |
| ⏳ Pending | `rules_oci` 2.3.0→2.3.1 | Not in BCR yet; retry next PR |
| ✅ Done | All GitHub Actions | checkout v6, setup-python v6, etc. |
| ✅ Done | Python libs | gunicorn 26, black 26, pytest 9, etc. |
| ⏳ Pending | Python 3.12→3.14 | No urgency; supported until Oct 2028 |

---

## Logistics for a fresh session

```bash
cd /Users/jorge/Projects/lillorepo
git checkout master && git pull --ff-only
```

Then read `CLAUDE.md` (root) + `.claude/CLAUDE.md` + this file.

Next action: **close PR #7 and start Phase B fresh** (dedicated
`biwenger-telegram-bot` service).

Useful shorthands:
- `/check-deps` — pinned versions vs latest
- `/release-notes` — when shipping a notable change
- `bazel test //core:core_tests //packages/biwenger_tools/{web,scraper_job,teams_analyzer}:*_tests`
- `flake8 core/ packages/ && black --check core/ packages/`
