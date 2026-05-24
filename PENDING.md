# Pending work

Long-running follow-ups that don't yet warrant a plan or PR.

**Rules of the file:**
- Never deleted; lives at the repo root.
- Lines are pruned as items ship or stop being relevant — keep it short.
- Group items by package; use `infra` for cross-cutting GCP/CI/policy tasks.
- "What has shipped" lives in `packages/biwenger_tools/release-notes.md` — do not duplicate here.

---

## infra

- **Drive folder cleanup** (USER-OWNED, week of 2026-05-26) — when the league ends:
  delete the Drive folder contents (the old CSVs the scraper used to upload), then
  drop the `biwenger-tools-sa-regional` secret or repoint it to a Sheets-only SA
  (Sheets API still authenticates through that mount for `ligas_especiales` /
  `trofeos`).
- **Standardise language in code** — comments, docstrings, variable names and log
  messages should be English everywhere. Telegram user-facing strings stay in
  Spanish (intentional, user-facing). Today there's a mix (some Spanish in
  variable names, ES/EN mixed in log messages).
- **Retry helper + apply consistently to outbound Biwenger POSTs** — today only
  `set_lineup` retries (hand-coded `_LINEUP_RETRY_BACKOFFS`). `place_market_bid`
  and the rest fail-fast on 5xx, which masks transient Biwenger blips. Wrap in a
  shared helper (tenacity or homegrown) and apply consistently.
- **Define an SLO + document it** — target ~5 min end-to-end for the daily
  process (JP fetch + Biwenger session + market read + N bids + Telegram). Land
  in `CLAUDE.md` or a new `docs/slo.md`. Today there's no articulated contract,
  so "system OK" is undefined.
- **Audit Claude memory** (`~/.claude/projects/-Users-jorge-Projects-lillorepo/memory/`) —
  promote anything load-bearing into `CLAUDE.md`; delete entries we've stopped
  using. Single source of truth principle, applied to memory.

## biwenger_tools/api

- **Refactor long orchestration functions** — `run_auto_bid` (166 LOC),
  `run_auto_pick_lineup` (207 LOC) and `run_daily` (121 LOC) each mix
  setup + business logic + side effects + error handling. Extract a
  `_OrchestratorContext` (JP+Biwenger+Firestore) and pure helpers so the
  orchestration is testable in isolation.
- **Split `test_api.py`** (~757 LOC) into focused files: `test_routes.py`,
  `test_recommendations.py`, `test_digests.py`. The auto-bid tests already
  live in `test_auto_bid.py` — same pattern for the rest.

## my_photos

- **Photo-recognition project** — tracked in `packages/my_photos/README.md`, not here.
