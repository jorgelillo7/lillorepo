# Next phases — pickup notes for a fresh session

This file is the entry point for any session continuing work in this repo.
Reads in 3 minutes; tells you what's done, what's next, and which decisions
are already taken.

## State on 2026-05-18

- **`master`**: clean after the v6.0 refactor landed. CI green. No open PRs.
- **Topology**: 4 Cloud Run **Services** + 1 Cloud Run **Job**.
  - `biwenger-summary` (web) ✅
  - `biwenger-api` (new) — Biwenger business logic over HTTP, `--no-allow-unauthenticated` ✅
  - `biwenger-bot` (renamed from `biwenger-telegram-bot`) — Telegram webhooks → calls `biwenger-api` ✅
  - `chucknorris-bot` — unchanged ✅
  - `biwenger-scraper-data` (Job, weekly Sun 22:00) ✅
- **Deleted**: `biwenger-teams-analyzer` Job. Its modes are now HTTP endpoints on `biwenger-api`.
- **Cloud Scheduler `biwenger-teams-analyzer-trigger`**: points at `biwenger-api/digests/daily` (daily 16:00 Madrid). Name is legacy; cosmetic rename is optional.
- **JP API**: alive, token unchanged. Read from `BIWENGER_CREDENTIALS_JSON.jp_auth_token`.
- **Python**: 3.13.
- **`python-base` image**: 275 MB (inside the 500 MB Artifact Registry free tier).
- **GCP secrets**: 4 JSON regional secrets only.
  - `biwenger-credentials-regional` — `{email, password, gdrive_folder_id, jp_auth_token}`
  - `telegram-bot-config-regional` — `{bot_token, chat_id, webhook_secret}`
  - `chucknorris-bot-config-regional` — `{bot_token, webhook_secret}`
  - `biwenger-tools-sa-regional` — Google Drive SA key (file mount at `/gdrive_sa/`)
- **Cost controls in place** unchanged from previous sprint (€1/month budget, log retention 7d, `scripts/check-gcp-costs.sh`).

## What shipped this sprint (2026-05-17 → 18)

PR 1 – PR 6 of `.claude/plans/biwenger_api_refactor.md` (now deleted, see release notes for the rundown):

* **PR 1 — skeleton**: new package `packages/biwenger_tools/api/`. Flask service with `GET /health` + `GET /version`. CI deploys `biwenger-api`.
* **PR 2 — daily digest**: `POST /digests/daily` moved out of the Job. Cloud Scheduler updated to OIDC + new URL. `/healthz` renamed to `/health` (Google Frontend reserves `/healthz` on `*.run.app`).
* **PR 3 — remaining modes**: `GET /teams`, `GET /teams/mine`, `GET /market`, `POST /lineups/auto-pick`. Bot now calls the api with an ID token; `job_trigger.py` deleted.
* **PR 4 — new endpoint**: `GET /budget/recommendations[?top=N]` + `/recomendar` command. Filters rivals' clausulable players by max bid, groups by primary position, returns top-N with multi-position badges.
* **PR 5 — rename + delete**: `telegram_bot` → `bot`, `biwenger-telegram-bot` → `biwenger-bot`. `teams_analyzer` package and Cloud Run Job deleted. Telegram webhook updated to new URL.
* **PR 6 — sweep**: READMEs, `docs/operations.md`, `docs/gcp.md`, `AGENTS.md`, CLAUDE.md, skills updated. Orphan Artifact Registry images (`telegram_bot`, `teams_analyzer`) deleted. Cost + cleanup scripts re-run green. v6.0 release notes.

---

## Pending work

### 1. Firestore migration (~16h, $0/mes) — DEFERRED
Deferred indefinitely by the user (2026-05-10).
Domain models in `core/domain/models.py` already map directly to Firestore. `google-firebase-basics` skill is already committed in `.claude/skills/` for when this resumes.

Agreed collection structure:
```
comunicados/{season}/messages/{id_hash}
clausulazos/{season}/transfers/{auto_id}
tabla_justicia/{season}/teams/{equipo}
participacion/{season}/authors/{autor}
palmares/{auto_id}
```

Attack order when resumed:
1. `core/sdk/firestore.py` — CRUD helpers, ADC auth
2. `scraper_job` — write to Firestore instead of CSV → Drive
3. `web` — read from Firestore instead of Drive CSVs
4. Delete secret `biwenger-tools-sa-regional` (Drive SA no longer needed)

### 2. (cosmetic) rename `biwenger-teams-analyzer-trigger` Scheduler
Currently points at `biwenger-api/digests/daily` but keeps the legacy name. Pure cosmetic — works as-is.

### 3. (cosmetic) rename bot display name in Telegram to "Biwenger Bot"
Done via BotFather (interactive). Optional.

### 4. New GCP project for photos (no spec yet)
Mentioned as TODO. Waiting for spec.

### 5. Move Drive/Sheets IDs out of BUILD.bazel
Currently hardcoded in `packages/biwenger_tools/web/BUILD.bazel`. Dies naturally with Firestore migration.

---

## Decisions already taken (don't reopen)

- Topology: bot → api (HTTP + ID token), api → Biwenger/JP/Telegram (sync). Cloud Scheduler → api/digests/daily.
- `--no-allow-unauthenticated` on `biwenger-api`; all callers (bot, scheduler) use OIDC with `roles/run.invoker` on the compute SA.
- `/health` (not `/healthz`) for liveness — GFE reserves the latter on `*.run.app`.
- `GET` for read-only endpoints (even when they send PNG as side effect); `POST` for state-mutating ones (`/lineups/auto-pick`, `/digests/daily`).
- Bot calls api **synchronously** with a 10-min timeout. The api processes the work and posts to Telegram itself. Bot returns 200 to Telegram once the api responds.
- Telegram bot → dedicated Cloud Run Service.
- Output (teams, market) → PNG via `sendPhoto`. No text/CSV.
- Recommendations are TEXT, not photos (per user preference).
- Auto-lineup captain → price < 3M strict, highest SF. Fallback: cheapest with known price.
- Chuck Norris bot → same GCP project (`biwenger-tools`). Regional secrets.
- Webhook helpers → `core/sdk/telegram.py`.
- Firestore migration → deferred; CSV/Drive stack stays.
- Web UI → Tailwind CDN + vanilla JS, no frameworks. Green palette #38a169.
- `.claude/plans/` → git-tracked. This file is pickup notes; per-feature plans are deleted once shipped.
- GCP secrets → JSON-consolidated, regional (`europe-southwest1`), free tier.
- Bots run with `cpu=0.5 concurrency=1`; api runs with `cpu=1 concurrency=10`; web stays `cpu=1 concurrency=80`.
- HTML sanitization → `bleach` with a fixed allowlist; no `|safe` anywhere in templates.
- Python base image → trimmed to runtime-only.

---

## Logistics for a fresh session

1. `cd /Users/jorge/Projects/lillorepo`
2. `git checkout master && git pull --ff-only`
3. Read `CLAUDE.md` (root) + `.claude/CLAUDE.md`.
4. Read this file.
5. Check open PRs: `gh pr list --state open`.

```bash
# Full test sweep
bazel test //core:core_tests \
  //packages/biwenger_tools/web:web_tests \
  //packages/biwenger_tools/scraper_job:scraper_job_tests \
  //packages/biwenger_tools/api:api_tests \
  //packages/biwenger_tools/bot:bot_tests \
  //packages/chucknorris_bot/bot:bot_tests

# Lint (same as CI)
python3 -m flake8 core/ packages/ && python3 -m black --check core/ packages/

# Cost + drift check
bash scripts/check-gcp-costs.sh

# Smoke biwenger-api
URL=$(gcloud run services describe biwenger-api --region europe-southwest1 --format='value(status.url)')
TOKEN=$(gcloud auth print-identity-token)
curl -H "Authorization: Bearer $TOKEN" $URL/health
curl -H "Authorization: Bearer $TOKEN" $URL/version
```

Do **not**:
- Commit directly to `master`.
- Touch `requirements_lock.txt` by hand.
- Add `Co-Authored-By` to commit messages.
- Bump dependencies in the same PR as a feature.
- Use `/healthz` as a Cloud Run path — Google Frontend reserves it.
