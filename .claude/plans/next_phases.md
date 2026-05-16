# Next phases — pickup notes for a fresh session

This file is the entry point for any session continuing work in this repo.
Reads in 3 minutes; tells you what's done, what's next, and which decisions
are already taken.

## State on 2026-05-16

- **`master`**: clean. PRs #36–#45 merged. CI green. No open PRs. No stale branches (local or remote).
- **JP API**: alive, token unchanged. Now read from `BIWENGER_CREDENTIALS_JSON.jp_auth_token` instead of hardcoded.
- **All packages in CI**: web, scraper_job, teams_analyzer, telegram_bot, chucknorris_bot.
- **Python**: 3.13.
- **`python-base` image**: 275 MB (down from 443 MB after slimming). Comfortably inside the 500 MB Artifact Registry free tier.
- **GCP secrets**: consolidated — 4 JSON regional secrets only.
  - `biwenger-credentials-regional` — `{email, password, gdrive_folder_id, jp_auth_token}`
  - `telegram-bot-config-regional` — `{bot_token, chat_id, webhook_secret}`
  - `chucknorris-bot-config-regional` — `{bot_token, webhook_secret}`
  - `biwenger-tools-sa-regional` — Google Drive SA key (file mount at `/gdrive_sa/`)
- **All Cloud Run services/jobs verified working** (2026-05-16):
  - `biwenger-summary` (web) ✅
  - `biwenger-telegram-bot` ✅ — `cpu=0.5 concurrency=1`
  - `chucknorris-bot` ✅ — `cpu=0.5 concurrency=1`
  - `biwenger-teams-analyzer` job ✅ (daily 16:00, also fan-out via /analizar)
  - `biwenger-scraper-data` job ✅ (weekly Sun 22:00)
- **Cost controls in place**:
  - €1/month budget with alerts at 50/90/100/150%
  - Log retention 7d on `_Default` bucket
  - `scripts/check-gcp-costs.sh` checks budget, retention, Cloud Run drift

## What shipped this sprint (2026-05-15 → 16)

### Naming + readability cleanup ✅ (PR #36)
- Entry points renamed (`get_messages.py` → `main.py`; `teams_analyzer.py` → `main.py`; `telegram_formatter.py` → `player_formatting.py`).
- `teams_analyzer.main()` refactored to a dispatch table; one handler per `ANALYSIS_MODE`.
- Magic numbers named (`SF_GREEN_THRESHOLD`, `SECONDS_PER_DAY`, `TELEGRAM_MAX_MESSAGE_LENGTH`).
- `_load_json_secret` deduped into `core/utils.load_json_secret`.

### Google Cloud skills synced ✅ (PR #37)
- `scripts/sync-google-skills.sh` pulls selected `SKILL.md`s from `github.com/google/skills` without the `npx skills add` third-party installer.
- 6 skills committed to `.claude/skills/google-*/`: cloud-run-basics, recipe-auth, waf-security, waf-reliability, waf-cost-optimization, firebase-basics.

### Security hardening ✅ (PR #38)
- `JP_AUTH_TOKEN` moved out of public git into `BIWENGER_CREDENTIALS_JSON.jp_auth_token`.
- XSS in announcements fixed: HTML sanitized in `web/sanitize.py`, applied via Jinja filter and eager pass in `_load_messages`. PR #40 later swapped the plain-text fallback for `bleach.clean` with a tag allowlist (rich formatting restored).
- `hmac.compare_digest` for the Telegram webhook secret.
- `SECRET_KEY` no longer falls back to `"default-dev-key"`; refuses to start in prod.
- CSRF on `/admin` and `/admin/run-scraper` forms (hand-rolled token in `web/csrf.py`).
- Session cookie flags: `HttpOnly`, `SameSite=Lax`, `Secure` (env-overridable for local HTTP).
- Webhook rejection logs `remote_addr` + `User-Agent`.

### Residual dedupes ✅ (PR #39)
- `MADRID_TZ`, `LEAGUE_ID`, `DRIVE_STALE_THRESHOLD` moved to `core/constants.py`.
- `SCORE_SF` removed from `lineup.py` (imports from `player_formatting`).

### Bleach for rich HTML ✅ (PR #40)
- `bleach==6.3.0` added across the five dependency layers + Docker base rebuild.
- `web/sanitize.safe_html` now uses `bleach.clean` with allowlist of `p, br, b, strong, em, i, u, a, ul, ol, li, blockquote, code`.

### GCP cost decisions + clean-images bug ✅ (PR #41)
- `chucknorris_bot` added to the `SIMPLE_IMAGES` array of `scripts/clean-images-artifact.sh` (it had quietly accumulated 8 stale digests).
- `docs/gcp.md` documents: `cpu=0.5+concurrency=1` for bots, log retention 7d, €1 budget, `jp_auth_token` co-located in the existing secret.

### Narrow exception handlers ✅ (PR #42)
- The 4 `core/sdk/telegram.py` wrappers and `web/routes/admin._trigger_scraper_job` now catch typed exceptions (`requests.RequestException` and `google.auth.exceptions.GoogleAuthError`). Top-level orchestrators and request handlers kept broad on purpose.

### Slim python-base image ✅ (PR #43)
- 443 MB → 275 MB (-38%). Three optimisations in one RUN layer: drop test/dev deps from the image, prune `googleapiclient/discovery_cache/documents` to just drive/sheets/run (was 581 files of 96 MB), `--no-compile` + cleanup of `__pycache__`, `.pyc`, pip cache, `/tmp`.
- Alpine considered and rejected (musl libc breaks/slowly recompiles numpy/matplotlib/pillow/cryptography wheels).

### Deploy.yml watches docker/ and MODULE.bazel ✅ (PR #44)
- Future changes to `Dockerfile.base` or the pinned digest in `MODULE.bazel` now trigger redeploys of every service automatically.

### check-gcp-costs.sh v3 + bots config baked into deploy.yml ✅ (PR #45)
- Three new checks: budget existence/amount (€1 EUR), log retention vs 7d, Cloud Run cpu/concurrency/minScale per service.
- `--cpu=0.5 --concurrency=1` baked into the bots' `gcloud run deploy` commands so no future `--image` update silently resets them.

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
5. Revisit Drive public-link permission decision (`gcp.py` makes uploads `anyone:reader`) — moot once Firestore lands.

### 2. Opus doc review (future, user-initiated)
Pass Opus over all MDs, docs, READMEs, diagrams across the repo. Done partially on 2026-05-16 for the refresh after the sprint.

### 3. New GCP project for photos (no spec yet)
Mentioned as TODO, no blockers. Waiting for spec.

### 4. Move Drive/Sheets IDs out of BUILD.bazel
Currently hardcoded in `packages/biwenger_tools/web/BUILD.bazel:13-19`.
Dies naturally with Firestore migration — no urgency until then.

---

## Decisions already taken (don't reopen)

- Telegram bot → dedicated Cloud Run Service, not the Flask web.
- Output (teams, market) → PNG via `sendPhoto`. No text/CSV.
- Auto-lineup captain → price < 3M strict, highest SF. Fallback: cheapest with known price.
- Chuck Norris bot → same GCP project (`biwenger-tools`). Regional secrets.
- Webhook helpers → `core/sdk/telegram.py`, not duplicated per bot.
- Firestore migration → deferred; CSV/Drive stack stays until explicitly resumed.
- Web UI → Tailwind CDN + vanilla JS, no frameworks. Same green palette #38a169.
- `.claude/plans/` → git-tracked. This file is the pickup-notes index, not a per-feature plan.
- GCP secrets → JSON-consolidated, regional (`europe-southwest1`), free tier.
- Bots run with `cpu=0.5 concurrency=1` (web stays `cpu=1 concurrency=80`).
- HTML sanitization → `bleach` with a fixed allowlist; no `|safe` anywhere in templates.
- Python base image → trimmed to runtime-only; test/dev deps live only in Bazel's hermetic sandbox.
- Alpine for Python base → no (musl libc is a trap for numpy/matplotlib/pillow/cryptography).

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
  //packages/biwenger_tools/teams_analyzer:teams_analyzer_tests \
  //packages/biwenger_tools/telegram_bot:telegram_bot_tests \
  //packages/chucknorris_bot/bot:bot_tests

# Lint (same as CI)
python3 -m flake8 core/ packages/ && python3 -m black --check core/ packages/

# Cost + drift check
bash scripts/check-gcp-costs.sh
```

Do **not**:
- Commit directly to `master`.
- Touch `requirements_lock.txt` by hand.
- Add `Co-Authored-By` to commit messages.
- Bump dependencies in the same PR as a feature.
