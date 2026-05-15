# Next phases — pickup notes for a fresh session

This file is the entry point for any session continuing work in this repo.
Reads in 3 minutes; tells you what's done, what's next, and which decisions
are already taken.

## State on 2026-05-13

- **`master`**: clean. PRs #21–#34 merged. CI green. No open PRs. No stale branches.
- **JP API**: alive, token unchanged.
- **All packages in CI**: web, scraper_job, teams_analyzer, telegram_bot, chucknorris_bot.
- **Python**: 3.13.
- **GCP secrets**: consolidated — 3 JSON regional secrets only.
  - `biwenger-credentials-regional` — `{email, password, gdrive_folder_id, jp_auth_token}` *(jp_auth_token added 2026-05-16 to remove the hardcoded JP token from public git; see `fix/security-hardening`)*
  - `telegram-bot-config-regional` — `{bot_token, chat_id, webhook_secret}`
  - `chucknorris-bot-config-regional` — `{bot_token, webhook_secret}`
  - `biwenger-tools-sa-regional` — Google Drive SA key (file mount at `/gdrive_sa/`)
- **All Cloud Run services/jobs verified working** (2026-05-13):
  - `biwenger-summary` (web) ✅
  - `biwenger-telegram-bot` ✅ (webhook 200)
  - `chucknorris-bot` ✅ (webhook 200)
  - `biwenger-teams-analyzer` job ✅ (executed successfully)
  - `biwenger-scraper-data` job ✅ (config correct)

## What shipped this sprint (2026-05-13)

### Mercado summary + filters ✅ (PR #24)
- Summary cards: total clausulazos, € movido, mayor gasto, último.
- Filter panel: text search + buyer/seller dropdowns + clear button.

### Secrets consolidation ✅ (PRs #25–#34)
- 9 individual GCP secrets → 3 JSON regional secrets.
- All `config.py` modules updated to read JSON first, fall back to individual env vars for local dev.
- All Cloud Run services/jobs updated via `gcloud run services/jobs update --set-secrets`.
- Cascading outages fixed: web service (remove-secrets), both bots (image rebuild PR #33), teams_analyzer job (config.py PR #34).

### docs/gcp.md ✅
- GCP services inventory + cost decisions documented.

### DESIGN.md gaps fixed ✅
- Mobile active nav state documented (`bg-green-50 text-green-700`).
- Card padding corrected to `24px (p-6)`.

---

## Pending work

### 1. Firestore migration (~16h, $0/mes) — DEFERRED
Deferred indefinitely by the user (2026-05-10).
Domain models in `core/domain/models.py` already map directly to Firestore.

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
4. Delete secrets `biwenger-tools-sa-regional` (Drive SA no longer needed)

### 2. Opus doc review (future, user-initiated)
Pass Opus over all MDs, docs, READMEs, diagrams across the repo.

### 3. New GCP project for photos (no spec yet)
Mentioned as TODO, no blockers. Waiting for spec.

### 4. Move Drive/Sheets IDs out of BUILD.bazel
Currently hardcoded in `packages/biwenger_tools/web/BUILD.bazel:13-19`.
Dies naturally with Firestore migration — no urgency until then.

---

## Closed / won't do

- **Audit and rotate SA key** — gitignored, never pushed. No risk.
- **Skills layout standardisation** — done PR #21.
- **season-rollover skill update** — done PR #22.
- **check-gcp-costs.sh v2** — done PRs #23/26/27.
- **Phase D dependencies** — up to date (2026-05-10).

---

## Decisions already taken (don't reopen)

- Telegram bot → dedicated Cloud Run Service, not the Flask web.
- Output (teams, market) → PNG via `sendPhoto`. No text/CSV.
- Auto-lineup captain → price < 3M strict, highest SF. Fallback: cheapest with known price.
- Chuck Norris bot → same GCP project (`biwenger-tools`). Regional secrets.
- Webhook helpers → `core/sdk/telegram.py`, not duplicated per bot.
- Firestore migration → deferred; CSV/Drive stack stays until explicitly resumed.
- Web UI → Tailwind CDN + vanilla JS, no frameworks. Same green palette #38a169.
- `.claude/plans/` → git-tracked (plans reference code paths, lifecycle cleanup on merge).
- GCP secrets → JSON-consolidated, regional (`europe-southwest1`), free tier.

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
```

Do **not**:
- Commit directly to `master`.
- Touch `requirements_lock.txt` by hand.
- Add `Co-Authored-By` to commit messages.
- Bump dependencies in the same PR as a feature.
