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
- **Cloud Scheduler `biwenger-daily-digest-trigger`**: points at `biwenger-api/digests/daily` (daily 09:00 Madrid, was 16:00 — moved on 2026-05-19 so the user sees the digest in the morning). Renamed from `biwenger-teams-analyzer-trigger` on 2026-05-18.
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

### 1. Firestore migration — SHIPPED (2026-05-21)

Done. Web reads from Firestore, scraper writes to Firestore, indexes
declared in `firestore.indexes.json`, schemas + read-cost reference in
`docs/firestore.md`. The CSV/Drive read path was retired in PR #82 and
the dual-write retired in the "part 2" cleanup PR. Drive folder
contents will be deleted by the user when the league ends.

The deferred-plan section that used to live here (with schemas, gotchas,
and the one-time backfill) is preserved in the git history at
commit 08c4a4e (`.claude/plans/firestore_pickup.md`) in case the
context is ever needed again.

Schemas, indexes, and read-cost reference live in `docs/firestore.md`.

**User-owned cleanup (week of 2026-05-26):** delete the Drive folder
contents, then drop the `biwenger-tools-sa-regional` secret (or repoint
it to a Sheets-only SA — Sheets API is still wired up).

### 2. New GCP project for photos (no spec yet)
Mentioned as TODO. Waiting for spec.

### 3. Move Drive/Sheets IDs out of BUILD.bazel
Currently hardcoded in `packages/biwenger_tools/web/BUILD.bazel`. Dies naturally with Firestore migration.

### 4. Bot display name in Telegram set to "Biwenger Tools Bot"
Done via BotFather on 2026-05-18.

---

## Mejoras propuestas (senior review 2026-05-19, ordenadas por impacto)

Surfaced during a code-review pass after the v6.0 refactor shipped. None
of these block anything; pick when ready.

1. **JP cache in the api.** Today `/alinear`, `/teams`, etc. pay ~5–10s of
   JP fetch per call. A 5-minute in-process cache on
   `core.sdk.jp.fetch_all_players` (the JP response is identical for all
   five endpoints within a few minutes) drops average request time to
   ~2s and reduces load on the private JP API. ~10 LoC with a TTL decorator.

2. **Cloud Run alerts for `biwenger-api` and the scraper job.** Free tier
   covers 5 alerts. Two minimum:
   - `biwenger-api` 5xx > 0 in a 5-minute window
   - Scraper job execution failed (now that the job re-raises on error,
     this is finally meaningful)
   The api already notifies Telegram on `/alinear` failure; Cloud Run alerts
   add coverage for the cases where the bot never even reaches the api
   (deploy regression, OIDC misconfiguration, etc.).

3. **`/alinear` dry-run mode.** `POST /lineups/auto-pick?dry_run=1` skips
   the Biwenger PUT and just sends "would have done X" to Telegram. ~10
   LoC plus a bot flag or a separate `/alinear?` syntax. Useful when you
   want to see what the picker would do without committing.

4. **Auto-register bot commands on deploy.** `setup_commands.py` is
   one-shot and manual today. Hook it into CI's `deploy-bot` job
   (post-deploy step). Doable in 1 step:
   `gcloud run jobs execute biwenger-bot-setup-commands` — or simpler,
   add a `setup-commands` step to the deploy.yml that uses
   `gcloud secrets versions access` + a few lines of curl.

5. **Single-tenant escape.** League ID, chat ID and user identity are
   hard-coded for one user. If a second pana wants to use it, ~1 sprint
   to extract per-user config into a Firestore `users/{user_id}`
   collection. Decision should drive whether to invest — if it's a
   personal project, fine to keep single-tenant.

6. **Tests mutate module-level `cfg.X`.** Works because pytest is serial.
   Migrate the relevant tests to use a `monkeypatch` fixture-injection
   pattern. Low priority — touched only when we modify those tests.

7. **Drive/Sheets IDs in `web/BUILD.bazel`.** Dies naturally with the
   Firestore migration; until then, env-vars would work fine.

8. **Documentation auto-render of the architecture diagram.** The
   Mermaid in `README.md` is hand-written and drifts. A small script
   that introspects `deploy.yml` + READMEs could regenerate it. Low
   priority.

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

# Lint (same Python 3.13 toolchain CI uses)
bash scripts/lint.sh

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
