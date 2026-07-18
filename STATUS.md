# Project status

Living maturity report for `lillorepo`. Updated as items from `PENDING.md` ship.
For feature-by-feature timelines, read `packages/biwenger_tools/release-notes.md`
and `packages/be_water/release-notes.md`. For the GCP inventory at a glance,
read `INFRA.md`.

**Current score: 9.4 / 10** (2026-05-24 audit, `biwenger_tools` scope — every
PENDING follow-up of that sprint shipped). **Cap under current constraints:
~9.5 / 10** (see _Accepted gaps_).

Since that audit the repo became **multi-product** — the score tracks the
mature biwenger platform; the newer packages ride the same machinery but are
younger by design.

---

## July 2026 — what changed since the audit

- **Be Water shipped end-to-end** (June README → public URL in 48 h, then
  productized through July): open catalog of Spanish bottled waters on its
  **own GCP project** (`be-water-app`) with Firestore, photo adds with Gemini
  label OCR, an admin-gated AI photo studio (nano banana + watermark),
  similarity recommender, public community ranking + achievements. 40 waters,
  OCU top-11 covered.
- **Cross-project CI** — one pipeline deploys both projects via the shared
  WIF service account (keyless); the cleanup job garbage-collects both
  Artifact Registry repos.
- **Cost model updated: strict €0 → sub-euro with hard caps.** The only paid
  call is the be_water studio photo (~$0.04, prepaid AI-Studio credits =
  impossible to overspend) plus Artifact Registry egress dust on deploy
  bursts. Guardrails: one €1 budget per project + one for Gemini,
  `scripts/check-gcp-costs.sh` audits both projects and the
  billing-account-wide Secret Manager free tier (6/6 versions in use).
- **`chucknorris_bot`** keeps running unchanged; **`my_photos`** exists as a
  plan (`packages/my_photos/README.md`), blocked on user-side disk work.
- **Claude memory strategy inverted** — the memory directory is deliberately
  empty; everything durable was ported into repo docs, skills and CLAUDE.md
  where any agent (or human) finds it.

---

## Inventory — what is built

| Layer | Component | Stack / GCP |
|---|---|---|
| **HTTP services** | `biwenger-api` — Biwenger business logic over REST | Cloud Run · Flask + gunicorn · `--no-allow-unauthenticated` (OIDC) |
| | `biwenger-bot` — Telegram webhook → calls api | Cloud Run · Flask · webhook secret validation |
| | `biwenger-summary` — analytics web | Cloud Run · Flask · Tailwind CDN + vanilla JS |
| | `chucknorris-bot` — joke bot, resurrected 2015 side project | Cloud Run · Flask · `chucknorris.io` |
| | `be-water` — public waters catalog (project `be-water-app`) | Cloud Run · Flask · Firestore + GCS photos · Gemini OCR/studio |
| **Jobs / workers** | `biwenger-scraper-data` — weekly board scraper | Cloud Run Job · Sun 22:00 · BeautifulSoup + Biwenger SDK |
| **Schedulers** | `biwenger-daily-digest-trigger` — `0 9 * * *` Europe/Madrid | Cloud Scheduler · OIDC POST → `/digests/daily` (chains auto-bid) |
| **Auto-bid engine** | `/market/auto-bid` + bot `/pujar` command | Tier table `min(price × multiplier, price + cap)` + jitter, Firestore idempotency, HTML-safe summary |
| **Lineup optimizer** | `/lineups/auto-pick` (+ `?dry_run=1`) | Memoised backtracking, captain MV cap, transient retry on Biwenger PUT |
| **Recommender** | `/budget/recommendations` (clausulazo targets) | `clause ≤ cash + dynamic margin`, sole-GK house rule |
| **Bot UX** | `/menu` inline keyboard + `/analizar` manager picker | Telegram callback_query dispatch |
| **Database** | Firestore native (`europe-southwest1`) ×2 projects | biwenger: `comunicados`, `participacion`, `clausulazos`, `tabla_justicia`, `palmares`, `auto_bid_log` (TTL 90d) · be-water: `waters`, `users` |
| | Composite index | `messages` by `categoria ASC + fecha DESC` |
| | TTL policy | `bids` collection-group via `expires_at` |
| **Sheets** | LIGAS_ESPECIALES + TROFEOS | Google Sheets API via SA mount (`biwenger-tools-sa-regional`) |
| **Object storage** | `be-water-photos` bucket (`us-central1` — deliberate: always-free tier is US-only) | Bottle photos, public read, EXIF stripped, 7-day tmp lifecycle |
| **Secret management** | 6 JSON regional secrets across 2 projects (account free tier: 6/6) | biwenger: credentials, telegram-bot-config, chucknorris-bot-config, tools-sa, flask-web-config · be-water: flask-web-config |
| **Reverse-engineered APIs** | Biwenger `/api/v2/*` | DevTools capture, documented in SDK |
| | Jornada Perfecta `/api/fitness-daily` | Token via Frida + Android JS bundle (see `frida-android-intercept.md`) |
| **Build system** | Bazel + bzlmod + rules_python + rules_oci + rules_pkg | `python_service` macro, shared layers, hermetic |
| **Container registry** | Artifact Registry `biwenger-docker` + `be-water-docker` | Multi-arch `python-base` + 6 per-service images; concurrency-gated cleanup post-deploy covers both repos |
| **CI/CD** | GitHub Actions `deploy.yml` | Detect changed → lint → test → per-module deploy (incl. cross-project `be-water` via WIF) → cleanup; `workflow_dispatch` fallback |
| **Lint / format** | flake8 + black (88 cols), hermetic via Bazel | CI gate before tests |
| **Tests** | pytest + requests-mock + MagicMock — 7 suites (core + 4 biwenger + chucknorris + be_water) | Ratio test/src **0.65** at the May audit |
| **Domain models** | `LeagueMessage`, `Participation`, `Clausulazo`, `JusticeEntry`, `Palmares` | Symmetric `from_firestore` / `to_firestore` |
| **Image rendering** | Squad / market tables → PNG | matplotlib, status emoji traffic light |
| **Security** | webhook secret HMAC, OIDC service-to-service, ADC for Firestore, HTML sanitisation (bleach), `/health` (NOT `/healthz`) | Zero key files in code path for Firestore |
| **Cost controls** | €1 budget per project (+1 for Gemini), log retention 7d, `min-instances=0`, Secret Manager at 6/6 account free tier, AR cleanup script, prepaid Gemini credits (hard cap) | `scripts/check-gcp-costs.sh` audits both projects + account totals |
| **Observability** | Structured JSON logs via `core.utils.get_logger` | Cloud Logging only — alerts intentionally out of scope (see below) |
| **Documentation** | `operations.md`, `gcp.md`, `firestore.md`, `INFRA.md`, per-package DESIGN.md + release-notes, `frida-android-intercept.md` | Maintained, no orphan docs |
| **AI / agents** | `.claude/skills/`, `.claude/hooks/`, AGENTS.md; memory deliberately empty (knowledge ported to repo docs) | Claude Code workflow integrated |
| **AI in product** | `core/sdk/gemini.py` — label OCR (free tier) + image generation (prepaid) | be_water photo-first add flow + admin studio |

---

## Strengths

1. **Test/src ratio 0.65** — uncommon for a personal project. The suite validates behaviour, not call patterns, and includes regression tests pinned to specific incidents (e.g. `test_format_telegram_text_html_escapes_user_content` references the 2026-05-24 silent fail).
2. **CI/CD maturity** — per-module change detection, OIDC service-to-service, cleanup race fixed with GH Actions `concurrency` group, `workflow_dispatch` as a manual safety net.
3. **Verifiable cost discipline** — sub-euro/month is real and hard-capped: free tiers respected on Secret Manager, Artifact Registry, Cloud Run, Firestore; the one paid API (Gemini image gen) runs on prepaid credits that cannot overspend. €1 budget alert per project.
4. **Idempotency by design** — SHA-256 doc IDs in the scraper, Firestore log keyed by `(date, player_id)` in auto-bid, `batch_write` + `delete_collection` helpers in the domain layer.
5. **Single source of truth doctrine** — `CLAUDE.md` (project charter), `PENDING.md` (follow-ups), per-package `release-notes.md` (history), `INFRA.md` (GCP inventory), this file (maturity). Claude memory deliberately empty: durable knowledge lives in the repo. No duplication.
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
| Mid-day 2026-05-24 (auto-bid + cost opts + HTML-safe fix) | 8.5 | +1.0 |
| Reply keyboard + Telegram-fail propagation everywhere | 8.7 | +0.2 |
| **All PENDING follow-ups shipped** (evening 2026-05-24) | **9.4** | +0.7 |
| Theoretical max under current constraints | ~9.5 | — |

Gap from baseline to today: **+1.9 points without spending a euro.**

---

## What shipped to get from 8.7 to 9.4

The 7 PENDING items closed in this final sprint:

| Item | PR |
|---|---|
| `OrchestratorContext` refactor — kill 4-way setup duplication in `actions` / `digests` / `recommendations` / `auto_bid` | #115 |
| Shared `core.sdk.http.retry_http_request` — applied to `set_lineup` AND `place_market_bid` | #114 |
| Split monolithic `test_api.py` (743 LOC) into `test_routes.py` / `test_recommendations.py` / `test_digests.py` | #111 |
| Spanish → English pass on code comments, docstrings and log messages (Telegram strings stay Spanish) | #112 |
| Define the daily-digest SLO (~5 min end-to-end) in `CLAUDE.md` | #113 |
| Audit Claude memory — promoted load-bearing entries, deleted 4 stale ones (13 → 9) | local |
| Persistent reply keyboard + cross-bot UX unification + `configure_bot_commands` helper | #105 / #108 / #109 / #110 |
