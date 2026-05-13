# Next phases — pickup notes for a fresh session

This file is the entry point for any session continuing work in this repo.
Reads in 3 minutes; tells you what's done, what's next, and which decisions
are already taken.

## State on 2026-05-13

- **`master`**: clean. PRs #21–#27 merged. CI green.
- **JP API**: alive, token unchanged.
- **All packages in CI**: web, scraper_job, teams_analyzer, telegram_bot, chucknorris_bot.
- **Python**: 3.13 (PR #18).
- **Open PR**: #25 — secrets consolidation (requires manual GCP secret creation before merging).

## What shipped this sprint (2026-05-13)

### Skills layout standardisation ✅ (PR #21)
- Shell scripts moved into `scripts/` subdirs within each skill folder.
- Affected: `check-deps/`, `rpi-common/` (shared by rpi-plan, rpi-implement, rpi-research).

### check-gcp-costs.sh v2 ✅ (PRs #23, #26, #27)
- Full rewrite covering Storage, Artifact Registry, Cloud Run Services/Jobs,
  Secret Manager, Cloud Scheduler, Logging.
- Summary table with OK/WARN/OVER status and free-tier percentages.
- bash 3.2 compatible (macOS default shell — no `declare -A`).

### season-rollover skill update ✅ (PR #22)
- Documents that teams_analyzer/telegram_bot/chucknorris_bot don't use TEMPORADA_ACTUAL.
- Added Step 2b: auto-generate palmarés CSV via `fetch_palmares.py`.
- New script: `.claude/skills/season-rollover/scripts/fetch_palmares.py`.

### Mercado summary + filters ✅ (PR #24)
- Summary cards: total clausulazos, € movido, mayor gasto (buyer+player), último.
- Filter panel: text search + buyer/seller dropdowns + clear button + counter.
- Client-side JS, no extra requests.

---

## Pending work

### 1. Secrets consolidation — PR #25 (blocked on manual GCP step)
Before merging #25, create the 4 consolidated secrets in GCP Secret Manager:
- `biwenger-credentials-regional` — JSON: `{"email": "...", "password": "...", "gdrive_folder_id": "..."}`
- `telegram-bot-config-regional` — JSON: `{"token": "...", "chat_id": "...", "webhook_secret": "..."}`
- `chucknorris-bot-config-regional` — JSON: `{"token": "...", "webhook_secret": "..."}`

Once created: merge PR #25, then delete the 9 old individual secrets.

### 2. Firestore migration (~16h, $0/mes) — DEFERRED
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
4. Delete secrets `gdrive-folder-id-regional` and `biwenger-tools-sa-regional`

### 3. Opus doc review (future)
Pass Opus over all MDs, docs, READMEs, diagrams across the repo.
No urgency — user-initiated when ready.

### 4. New GCP project for photos (no spec yet)
Mentioned as TODO, no blockers. Waiting for spec.

---

## Closed / won't do

- **Audit and rotate SA key** — gitignored, never pushed. No risk.
- **Move Drive/Sheets IDs to Secret Manager** — dies with Firestore migration.
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
