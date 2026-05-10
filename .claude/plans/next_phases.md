# Next phases — pickup notes for a fresh session

This file is the entry point for any session continuing work in this repo.
Reads in 3 minutes; tells you what's done, what's next, and which decisions
are already taken.

## State on 2026-05-10

- **`master`**: clean. All A/B/C phases shipped.
- **JP API**: alive, token unchanged.
- **`teams_analyzer_rewrite.md`**: deleted — all three phases implemented.

## What shipped (Phases A, B, C)

### Phase A — teams_analyzer on Cloud Run ✅
Daily Cloud Run Job `biwenger-teams-analyzer` running at 16:00 Madrid.
CI auto-deploys on changes to `packages/biwenger_tools/teams_analyzer/**`.
Image in Artifact Registry. Cleanup script working.

### Phase B — Telegram bot ✅
Implemented as a **dedicated Cloud Run Service** (`biwenger-telegram-bot`),
not the Flask web (plan said Option A but dedicated service was cleaner).
Module: `packages/biwenger_tools/telegram_bot/`.
Commands registered: `/analizar`, `/myteam`, `/mercado`, `/alinear`, `/help`.
Webhook validated with `X-Telegram-Bot-Api-Secret-Token`.
CI auto-deploys on `packages/biwenger_tools/telegram_bot/**` changes.

### Phase C — Auto-lineup `/alinear` ✅
`pick_lineup()` in `teams_analyzer/logic/lineup.py`.
Greedy formation search over 12 formations, multi-position support via
`altPositions` field discovered in Biwenger API (was the open research question).
Captain: price < 3M → highest SF; fallback: highest SF overall.
Dry-run exposed as preview step in `/alinear` before applying.
`BiwengerClient.set_lineup()` added to `core/sdk/biwenger.py`.

## Decisions already taken (don't reopen)

- Telegram bot → **dedicated Cloud Run Service**, not the Flask web.
  The Flask web (`biwenger-summary`) stays focused on data visualisation.
- Multi-position → `altPositions` field in Biwenger API (array of pos IDs).
  `BiwengerClient.get_manager_squad()` already returns it; lineup builder reads it.
- Auto-lineup captain rule → price < 3M preferred (double points in Biwenger),
  then highest SF. This is locked in `logic/lineup.py`.
- All output modes (my_team, market, all, alinear, daily) send **PNG images**
  via `sendPhoto`, not text/CSV. `send_telegram_document` removed from core.
- `telegram_formatter.py` is now a thin helpers module (5 functions) used only
  by `image_formatter.py`. All text/CSV builders deleted.

---

## Phase D — Dependency maintenance (next priority)

These are standalone PRs; none block each other. Do them in order.
Run `/check-deps` first to confirm latest versions.

| Order | Bump | Files | Risk |
|-------|------|-------|------|
| 1st | `rules_python` 0.40.0 → 2.0.0 | `MODULE.bazel`, `*/BUILD.bazel` if deprecated APIs used | Medium |
| 1st | `platforms` 0.0.10 → 1.1.0 | `MODULE.bazel` | Low |
| 2nd | GitHub Actions: checkout v6, setup-python v6, setup-bazel 0.19.0, paths-filter v4, google-github-actions/* v3 | `.github/workflows/deploy.yml` | Low; drop `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` in same PR |
| 3rd | Python libs: gunicorn 23→25, pytest 8→9, black 25→26, google-api-python-client + google-auth latest | per-module `requirements.txt`, regen lock, rebuild + repush `Dockerfile.base`, update digest in `MODULE.bazel` | Medium |
| Last | Python 3.12 → 3.14 | `MODULE.bazel`, `Dockerfile.base`, CI, lock regen | High — only if there's a reason; 3.12 supported until Oct 2028 |

---

## Other open work (not urgent)

- **Auditar y rotar SA key** — if the key in the repo is real (~30min).
- **Mover IDs de Drive/Sheets a Secret Manager** — currently hardcoded in
  `packages/biwenger_tools/web/BUILD.bazel:13-19`.
- **Sección VAR en web** — trigger manual del AI scraper o cron job.
- **Migración CSV → Firestore** — domain models ready; no urgency.

---

## Logistics for a fresh session

1. `cd /Users/jorge/Projects/lillorepo`
2. `git checkout master && git pull --ff-only`
3. Read `CLAUDE.md` (root) + `.claude/CLAUDE.md`.
4. Read this file.
5. Default next action: **Phase D** (pick the first pending bump).

Useful shorthands:

```bash
# Full test sweep
bazel test //core:core_tests \
  //packages/biwenger_tools/web:web_tests \
  //packages/biwenger_tools/scraper_job:scraper_job_tests \
  //packages/biwenger_tools/teams_analyzer:teams_analyzer_tests \
  //packages/biwenger_tools/telegram_bot:telegram_bot_tests

# Lint (same as CI)
flake8 core/ packages/ && black --check core/ packages/

# Register bot commands (run manually after adding a command)
TELEGRAM_BOT_TOKEN=xxx PYTHONPATH=. python3 \
  packages/biwenger_tools/telegram_bot/setup_commands.py
```

Do **not**:

- Commit directly to `master` (CI deploys on push).
- Touch `requirements_lock.txt` by hand.
- Add `Co-Authored-By` to commit messages.
- Bump dependencies in the same PR as a feature.
