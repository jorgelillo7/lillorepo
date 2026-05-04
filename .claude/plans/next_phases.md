# Next phases — pickup notes for a fresh session

This file is the entry point for any session continuing the work after the JP
rewrite (v4.2). Reads in 3 minutes; tells you what's done, what's next, and
which decisions are already taken so you don't ask again.

## State on 2026-05-04

- **`master`**: clean. v4.2 already shipped (PR #3 merged on 2026-05-03).
- **PR #4 open** (`chore/rebuild-python-base`): rebuilds `python-base` without
  Selenium/pytz/trio* + fixes the AR cleanup script that wasn't deleting
  anything (`get(digest)` → `value(version)` bug). **Wait for it to merge
  before starting Phase A** — the slim base image and a working cleanup are
  pre-requisites for adding the teams_analyzer Cloud Run Job without crossing
  the AR free tier.
- **JP API**: alive, token unchanged, 546 players, Nico Williams SF=571 ✓.
- **Active plan**: `.claude/plans/teams_analyzer_rewrite.md` (still relevant for
  Phase B and Phase C below — do not delete until those ship).

## Decisions already taken (don't reopen)

- Telegram bot architecture → **webhook on the existing Flask web** (Option A
  of `teams_analyzer_rewrite.md`). The web is always alive on Cloud Run, so
  we get the bot for free. Do not introduce a separate Cloud Run service or
  long-polling job.
- Auto-lineup endpoint (`PUT /api/v2/user`) confirmed working from the dev
  tools session. Body shape documented in `teams_analyzer_rewrite.md` §
  "API de Biwenger — Alineación".
- Domain models (`LeagueMessage`, `Participation`, `Clausulazo`,
  `JusticeEntry`) **are applied** to the data path. Don't refactor them out
  unless you have a strong reason — they're the contract that makes the future
  Firestore migration localised.

---

## Phase A — Deploy teams_analyzer to Cloud Run Job (~30 min)

**Goal:** the analyzer runs daily at 16:00 Madrid time, pushing Telegram
messages, with zero coste accumulating.

**Pre-req:** PR #4 merged. Without it, the new image will fatten Artifact
Registry past the 500MB free tier.

### Steps

1. **Create the two Telegram secrets in Secret Manager** (Biwenger ones already
   exist):

   ```bash
   echo -n "<TELEGRAM_BOT_TOKEN>" | gcloud secrets create telegram-bot-token-regional \
       --replication-policy="user-managed" --locations=europe-southwest1 --data-file=-

   echo -n "<TELEGRAM_CHAT_ID>" | gcloud secrets create telegram-chat-id-regional \
       --replication-policy="user-managed" --locations=europe-southwest1 --data-file=-
   ```

2. **Push the image to Artifact Registry**:

   ```bash
   bazel run //packages/biwenger_tools/teams_analyzer:push_image_to_gcp \
       --platforms=//platforms:linux_amd64
   ```

3. **Create the Cloud Run Job**. Mirror the scraper exactly (memory 512Mi,
   cpu 1, retries 0, max 1 task). The teams_analyzer needs Biwenger creds
   from existing secrets, plus the two new Telegram ones, mounted as env vars
   (the analyzer reads `os.getenv` directly):

   ```bash
   gcloud run jobs create biwenger-teams-analyzer \
       --image=europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/teams_analyzer:latest \
       --region=europe-southwest1 \
       --memory=512Mi --cpu=1 \
       --max-retries=0 --task-timeout=300s \
       --set-secrets="BIWENGER_EMAIL=biwenger-email-regional:latest,BIWENGER_PASSWORD=biwenger-password-regional:latest,TELEGRAM_BOT_TOKEN=telegram-bot-token-regional:latest,TELEGRAM_CHAT_ID=telegram-chat-id-regional:latest"
   ```

   Note: the analyzer reads env vars (`config.py` does `os.getenv("BIWENGER_EMAIL")`)
   so we use `--set-secrets=ENV_NAME=secret:latest`, **not** the file-mount
   form the scraper uses. The scraper reads from `/biwenger_email/biwenger-email`
   files because its `read_secret_from_file` helper is wired that way.

4. **Schedule it**. Same pattern as
   `biwenger-scraper-data-scheduler-trigger` (location europe-west1, OAuth
   token to the Run API):

   ```bash
   PROJECT_NUMBER=$(gcloud projects describe biwenger-tools --format='value(projectNumber)')

   gcloud scheduler jobs create http biwenger-teams-analyzer-trigger \
       --location=europe-west1 \
       --schedule="0 16 * * *" \
       --time-zone="Europe/Madrid" \
       --uri="https://europe-southwest1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/biwenger-tools/jobs/biwenger-teams-analyzer:run" \
       --http-method=POST \
       --oauth-service-account-email="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
       --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
   ```

5. **Wire CI** to redeploy the analyzer image automatically when its code
   changes. Add a `deploy-teams-analyzer` job in `.github/workflows/deploy.yml`
   mirroring `deploy-scraper`. Also add `teams_analyzer` to the
   `detect-changes` paths-filter (already covered if you copy the pattern).
   Reference: see how `deploy-scraper` handles `gcloud run jobs update` after
   the `push_image_to_gcp`.

6. **Smoke test the deploy**:

   ```bash
   gcloud run jobs execute biwenger-teams-analyzer --region=europe-southwest1 --wait
   ```

   Confirm Telegram messages arrive (own squad, market, rivals).

### Done criteria

- Cron fires every day at 16:00 Madrid.
- Manual `gcloud run jobs execute` works.
- A code change in `packages/biwenger_tools/teams_analyzer/**` deploys via CI.
- Artifact Registry stays under 500MB after a few cycles (cleanup script does
  its job — verified in PR #4).

### Open question

The free tier on Cloud Scheduler is 3 jobs/month forever. With this you'll
have 2 jobs (scraper + analyzer). Still 1 spare slot before charges kick in.

---

## Phase B — Telegram bot interactivo (Phase 2 of the analyzer plan)

**Goal:** type `/analizar` in the Telegram chat → the analyzer runs on demand
and posts results, without waiting for the daily cron.

**Pre-req:** Phase A done — the analyzer image must already exist in AR and
the secrets must be in Secret Manager.

### Architecture (already decided)

Webhook handler inside the existing Flask app. New blueprint
`packages/biwenger_tools/web/routes/telegram.py`. Single endpoint
`POST /telegram/webhook` that:

1. Parses the Telegram update.
2. Validates `chat.id == TELEGRAM_CHAT_ID` (single-tenant — only your chat).
3. Routes by `message.text`:
   - `/analizar` → kick off the analyzer flow (see step 3 below).
   - `/help` → static help text listing available commands.
   - anything else → ignore silently.

### Implementation outline

1. **Refactor the analyzer entry point** so it can be called as a function,
   not just `python -m`. Today `teams_analyzer.main()` already exists and is
   self-contained — perfect. Just move the `if __name__ == "__main__"` guard
   so `main()` is importable from the web.

2. **Webhook validation**. Telegram sends a header `X-Telegram-Bot-Api-Secret-Token`
   if you registered the webhook with `secret_token`. Generate a random secret,
   store it as `TELEGRAM_WEBHOOK_SECRET` in Secret Manager, set it both at
   `setWebhook` time and validated in the handler. Without this anyone could
   POST garbage to `/telegram/webhook` and crash the web.

3. **Async or sync?** Cloud Run Service request timeout default is 300s. The
   analyzer takes ~10-15s wall (1 JP request + 1 Biwenger login + N squads).
   So **synchronous handling is fine** — no Pub/Sub or background queue
   needed. If it ever creeps over 60s, switch to "ack the webhook with 200,
   spawn a thread, post results when done" but don't pre-optimise.

4. **Register the webhook once** (manual, one-time):

   ```bash
   curl -X POST "https://api.telegram.org/bot$TOKEN/setWebhook" \
        -d "url=https://biwenger-summary-pjpqofuevq-no.a.run.app/telegram/webhook" \
        -d "secret_token=$TELEGRAM_WEBHOOK_SECRET" \
        -d "allowed_updates=[\"message\"]"
   ```

5. **Tests**: Flask test client + mocked `teams_analyzer.main`. Validate:
   - Wrong chat_id returns 200 silently (Telegram retries on non-200 — never
     return 4xx unless you really want to drop the update).
   - Missing/wrong secret token returns 401.
   - `/analizar` from the right chat_id triggers `main()` once.
   - Unknown commands are ignored.

### Things NOT to do in Phase B

- Don't add `/alinear` here — that's Phase C and has unresolved research.
- Don't add caching of the last analysis — premature; one extra HTTP call is
  cheap.
- Don't add rate limiting — single-tenant chat, the only attacker is yourself.
  If it becomes a problem, add it later.

### Done criteria

- Sending `/analizar` from your chat triggers a fresh analysis.
- Sending `/analizar` from any other chat does nothing visible.
- Webhook handler has unit tests.
- Web README mentions the new endpoint.

---

## Phase C — Auto-lineup (Phase 3 of the analyzer plan)

**Goal:** `/alinear` reads your squad, picks the best XI according to JP
predict-SF, sets a captain (price < 3M tie-breaker by SF), and PUTs the
lineup to Biwenger.

**Pre-req:** Phase B done. **AND a research spike on multi-position must be
finished first** — see below.

### ⚠️ The blocker before any code: multi-position research

The Biwenger API endpoint we use for squads (`/api/v2/user/{id}?fields=players(id,owner)`)
returns each player's `position` as a single int (1=GK, 2=DEF, 3=MID, 4=FWD).
But on the Biwenger UI some players list two positions — defenders that can
play as midfielders, etc. If we build the lineup using only the API's
single position field, we'll mis-place dual-role players (and the server
will reject the formation).

**Before writing any `/alinear` code**, do this research spike:

1. Inspect the dev-tools network tab while loading the squad page in
   Biwenger's web. Look for any endpoint that returns players with a
   `positions: [2, 3]` array or similar.
2. If found, document the URL + shape in
   `docs/technical/reverse-engineering/biwenger-api.md` and add a method
   to `BiwengerClient` that fetches it.
3. If not found, fall back to maintaining a manual override map
   (`{player_id: [2, 3]}`) for the handful of dual-role players. Live with
   the maintenance cost.
4. **Write down the answer in `teams_analyzer_rewrite.md` § "FASE 3 →
   Pendiente de investigar"** before closing the spike. Don't proceed
   without that resolution recorded.

### Implementation outline (post-research)

1. **`/alinear` handler** in the same telegram blueprint. Same chat_id +
   secret_token validation as Phase B.

2. **Lineup builder**:

   - Fetch JP players + Biwenger squad (reuse the orchestrator helpers).
   - Filter available: `status not in {injured, suspended}` AND
     `nextMatch.status == "pending"` AND `nextMatch.playerInLineup == True`.
   - For each formation in the supported list (3-4-3, 3-5-2, 4-3-3, ...),
     compute the best XI by greedy assignment to slots and sum the SF
     ratings. Keep the formation with max total.
   - For multi-position players, allow them in any of their slots.

3. **Captain pick**: among the chosen XI, prefer players with `price < 3000000`
   (Biwenger's "low cost = double points" rule). Among them, pick the
   highest predict-SF. If none qualify, pick the highest predict-SF overall.

4. **Apply via Biwenger SDK**: add `BiwengerClient.set_lineup(formation,
   players, reserves, captain)` that wraps `PUT /api/v2/user?fields=*,lineup(date)`.
   Body shape documented in `teams_analyzer_rewrite.md` § "Request body".

5. **Confirmation message**: post the chosen XI back to Telegram with the
   formation, captain, and a one-line summary (sum of predicted points).

### Things to be careful with

- **`playersID` order matters** (per the spike note in the original plan).
  Most likely GK → DEF → MID → FWD by formation. Confirm with one careful
  test against your real account before shipping.
- **`reservesID` is `(int|null)[]`** with positional nulls. Don't filter
  out nulls.
- **Validate the formation server-side**. Send one obviously-wrong lineup
  first to learn what the API rejects.
- **Don't ship without a `--dry-run`** mode. Have `/alinear preview` that
  prints the chosen XI without PUTting, plus `/alinear` that actually
  applies. Test `preview` first.

### Done criteria

- `/alinear preview` shows the proposed XI + captain.
- `/alinear` applies it and the change is visible in the Biwenger app.
- Multi-position players land in valid slots.
- All `set_lineup` paths covered by tests with mocked HTTP.

---

## Phase D — Dependency maintenance (independent, anytime)

These are the upgrades flagged by `/check-deps`. Each is a standalone PR;
none block any of the phases above.

| Order | Bump | Files to touch | Risk |
|-------|------|----------------|------|
| 1st (urgent) | `rules_python` 0.40.0 → 2.0.0 | `MODULE.bazel`, possibly `*/BUILD.bazel` if any used deprecated APIs | Medium — re-run `bazel build //...` and fix any rule changes |
| 1st (urgent) | `platforms` 0.0.10 → 1.1.0 | `MODULE.bazel` | Low |
| 2nd | GitHub Actions: `checkout` v4→v6, `setup-python` v5→v6, `setup-bazel` 0.8.5→0.19.0, `paths-filter` v3→v4, `google-github-actions/auth` v2→v3, `google-github-actions/setup-gcloud` v2→v3 | `.github/workflows/deploy.yml` | Low; remove the `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` flag in the same PR |
| 3rd | Python libs: `gunicorn` 23→25, `pytest` 8→9, `black` 25→26, `google-api-python-client` and `google-auth` to latest | per-module `requirements.txt`, regenerate `requirements_lock.txt`, **rebuild and repush `Dockerfile.base`**, update digest in `MODULE.bazel`, also bump `black` pin in CI lint job | Medium (test plugins, formatter changes) |
| Last | Python 3.12 → 3.14 | `MODULE.bazel`, `Dockerfile.base`, workflow lint job, `requirements_lock.txt` regen with new interpreter | High (compat surprises) — only if there's a reason; 3.12 supported until Oct 2028 |

Run `/check-deps` first to confirm latest versions before opening any of these.

---

## Logistics for a fresh session

When you start the new session, do this in order:

1. `cd /Users/jorge/Projects/lillorepo`
2. `git checkout master && git pull --ff-only`
3. Read `CLAUDE.md` (root) + `.claude/CLAUDE.md` for repo conventions.
4. Read this file (`.claude/plans/next_phases.md`).
5. Pick the next phase. If unsure, default to: A → B → D (parallel) → C.

Useful shorthand:

- `bash .claude/skills/check-deps/check_deps.sh` — pinned-versions snapshot.
- `/check-deps` — same + comparison vs latest releases.
- `/release-notes` — when shipping a notable change.
- `bazel test //core:core_tests //packages/biwenger_tools/{web,scraper_job,teams_analyzer}:*_tests` — full test sweep.
- `flake8 core/ packages/ && black --check core/ packages/` — same lint as CI.

Do **not**:

- Commit directly to `master` (CI deploys on push).
- Touch `requirements_lock.txt` by hand.
- Add `Co-Authored-By` to commit messages (per user memory).
- Bump dependencies in the same PR as a feature — keep them separate.
