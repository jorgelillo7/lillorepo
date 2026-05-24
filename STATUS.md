# Project status

Living maturity report for `lillorepo`. Updated as items from `PENDING.md` ship.
For a feature-by-feature timeline, read `packages/biwenger_tools/release-notes.md`.

**Current score: 8.5 / 10** (senior-dev audit, 2026-05-24).
**Projected score after the PENDING follow-ups: ~9.45 / 10.**

The remaining 0.55 is a deliberate cap (see _Accepted gaps_ below).

---

## Inventory — what is built

| Layer | Component | Stack / GCP |
|---|---|---|
| **HTTP services** | `biwenger-api` — Biwenger business logic over REST | Cloud Run · Flask + gunicorn · `--no-allow-unauthenticated` (OIDC) |
| | `biwenger-bot` — Telegram webhook → calls api | Cloud Run · Flask · webhook secret validation |
| | `biwenger-summary` — analytics web | Cloud Run · Flask · Tailwind CDN + vanilla JS |
| | `chucknorris-bot` — joke bot, resurrected 2015 side project | Cloud Run · Flask · `chucknorris.io` |
| **Jobs / workers** | `biwenger-scraper-data` — weekly board scraper | Cloud Run Job · Sun 22:00 · BeautifulSoup + Biwenger SDK |
| **Schedulers** | `biwenger-daily-digest-trigger` — `0 9 * * *` Europe/Madrid | Cloud Scheduler · OIDC POST → `/digests/daily` (chains auto-bid) |
| **Auto-bid engine** | `/market/auto-bid` + bot `/pujar` command | Tier table `min(price × multiplier, price + cap)` + jitter, Firestore idempotency, HTML-safe summary |
| **Lineup optimizer** | `/lineups/auto-pick` (+ `?dry_run=1`) | Memoised backtracking, captain MV cap, transient retry on Biwenger PUT |
| **Recommender** | `/budget/recommendations` (clausulazo targets) | `clause ≤ cash + dynamic margin`, sole-GK house rule |
| **Bot UX** | `/menu` inline keyboard + `/analizar` manager picker | Telegram callback_query dispatch |
| **Database** | Firestore native (`europe-southwest1`) | Collections: `comunicados`, `participacion`, `clausulazos`, `tabla_justicia`, `palmares`, `auto_bid_log` (TTL 90d) |
| | Composite index | `messages` by `categoria ASC + fecha DESC` |
| | TTL policy | `bids` collection-group via `expires_at` |
| **Sheets** | LIGAS_ESPECIALES + TROFEOS | Google Sheets API via SA mount (`biwenger-tools-sa-regional`) |
| **Secret management** | 4 JSON regional secrets | `biwenger-credentials`, `telegram-bot-config`, `chucknorris-bot-config`, `biwenger-tools-sa` |
| **Reverse-engineered APIs** | Biwenger `/api/v2/*` | DevTools capture, documented in SDK |
| | Jornada Perfecta `/api/fitness-daily` | Token via Frida + Android JS bundle (see `frida-android-intercept.md`) |
| **Build system** | Bazel + bzlmod + rules_python + rules_oci + rules_pkg | `python_service` macro, shared layers, hermetic |
| **Container registry** | Artifact Registry `biwenger-docker` | Multi-arch `python-base` + 5 per-service images; concurrency-gated cleanup post-deploy |
| **CI/CD** | GitHub Actions `deploy.yml` (~465 LOC) | Detect changed → lint → test → per-module deploy → cleanup; `workflow_dispatch` fallback |
| **Lint / format** | flake8 + black (88 cols), hermetic via Bazel | CI gate before tests |
| **Tests** | pytest + requests-mock + MagicMock — 6 suites | Ratio test/src **0.65** |
| **Domain models** | `LeagueMessage`, `Participation`, `Clausulazo`, `JusticeEntry`, `Palmares` | Symmetric `from_firestore` / `to_firestore` |
| **Image rendering** | Squad / market tables → PNG | matplotlib, status emoji traffic light |
| **Security** | webhook secret HMAC, OIDC service-to-service, ADC for Firestore, HTML sanitisation (bleach), `/health` (NOT `/healthz`) | Zero key files in code path for Firestore |
| **Cost controls** | Budget alert €1/month, log retention 7d, `min-instances=0`, Secret Manager kept under free tier, AR cleanup script | `scripts/check-gcp-costs.sh` for audit |
| **Observability** | Structured JSON logs via `core.utils.get_logger` | Cloud Logging only — alerts intentionally out of scope (see below) |
| **Documentation** | `operations.md` (17K), `gcp.md` (6K), `firestore.md` (11K), DESIGN.md, release-notes, `frida-android-intercept.md` | Maintained, no orphan docs |
| **AI / agents** | `.claude/skills/`, `.claude/hooks/`, AGENTS.md, persistent memory (~13 curated entries) | Claude Code workflow integrated |

---

## Strengths

1. **Test/src ratio 0.65** — uncommon for a personal project. The suite validates behaviour, not call patterns, and includes regression tests pinned to specific incidents (e.g. `test_format_telegram_text_html_escapes_user_content` references the 2026-05-24 silent fail).
2. **CI/CD maturity** — per-module change detection, OIDC service-to-service, cleanup race fixed with GH Actions `concurrency` group, `workflow_dispatch` as a manual safety net.
3. **Verifiable cost discipline** — €0/month is real, not aspirational. Free tier respected on Secret Manager, Artifact Registry, Cloud Run, Firestore. Budget alert at €1.
4. **Idempotency by design** — SHA-256 doc IDs in the scraper, Firestore log keyed by `(date, player_id)` in auto-bid, `batch_write` + `delete_collection` helpers in the domain layer.
5. **Single source of truth doctrine** — `CLAUDE.md` (project charter), `PENDING.md` (follow-ups), `release-notes.md` (history), Claude memory (cross-session context). No duplication.
6. **Security hygiene** — webhook HMAC validation, OIDC bot↔api, regional secrets, ADC for Firestore (no key files), HTML sanitisation in templates.
7. **Reverse engineering documented** — `frida-android-intercept.md` records how the JP token was captured. The Biwenger `/offers` endpoint was reverse-engineered live from a curl capture.
8. **Defensive patterns at the right boundaries** — exponential backoff on the Biwenger lineup PUT, JP cache freshness probe, GFE `/healthz` reservation workaround, HTML-escape on Telegram payloads — each one is a codified lesson learned.

---

## Accepted gaps (intentional — they cap the score)

Three improvements would push the score above ~9.5 but were explicitly skipped to preserve the project's constraints (single user, €0/month, side-project scope):

| Gap | Why skipped | Score it would unlock |
|---|---|---|
| **Real observability** (Cloud Monitoring alerts, SLI dashboards, error-rate tracking) | Would push past the free tier; current Cloud Logging is enough for a human-driven workflow | +0.20 |
| **Staging environment** | Local + prod is sufficient for one user; every merge already deploys and the rollback path is fast | +0.15 |
| **Integration tests** against Firestore emulator / Biwenger sandbox | Heavy setup for low marginal value at this traffic — unit tests + careful HTTP boundary mocking catch most regressions | +0.15 |

Total cap: **~9.5 / 10** without breaking the side-project constraints.

---

## Score progression

| Milestone | Score | Delta |
|---|---|---|
| Baseline (pre-Firestore, May 2026) | 7.5 | — |
| Today (post auto-bid + cost opts + HTML-safe fix) | **8.5** | +1.0 |
| Projected (after PENDING items ship) | **~9.45** | +0.95 |
| Theoretical max under current constraints | ~9.5 | — |

Gap from baseline to projected: **+1.95 points without spending a euro.**

---

## Path to 9.45

The 7 follow-ups tracked in `PENDING.md`:

| Item | Δ score |
|---|---|
| Refactor long orchestration functions (`run_auto_bid` 166 LOC, `run_auto_pick_lineup` 207 LOC, `run_daily` 121 LOC) into context + pure helpers | +0.25 |
| Propagate `send_telegram_message`'s `bool` return to every caller (today only auto-bid surfaces failures) | +0.20 |
| Retry helper applied consistently to outbound Biwenger POSTs (today only `set_lineup` retries) | +0.20 |
| Split monolithic `test_api.py` (~757 LOC) into per-feature files | +0.10 |
| Standardise code language to English (variables, comments, log messages — Telegram user-facing strings stay in Spanish) | +0.10 |
| Define and document an SLO target (~5 min end-to-end for the daily process) | +0.10 |
| Audit Claude memory: promote load-bearing entries to `CLAUDE.md`, delete stale ones | +0.05 |

Each of these is scoped to a single PR. Nothing requires recurring spend.
