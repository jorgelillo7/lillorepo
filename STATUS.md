# Project status

Living maturity report for `lillorepo`. Updated as items from `PENDING.md` ship.
For feature-by-feature timelines read `packages/biwenger_tools/release-notes.md`
and `packages/be_water/release-notes.md`. For the GCP inventory at a glance,
read `INFRA.md`.

**Current score: 9.4 / 10** (2026-07-26 review). **Cap under current
constraints: ~9.5 / 10** (see _Accepted gaps_). The repo is now genuinely
**multi-product**; the score tracks the whole estate, weighted toward the
mature biwenger platform. The July quality-hardening pass (26 Jul) closed the
be_water coverage drag that held the previous review at 9.3 — measured line
coverage now sits at **80% repo-wide**, be_water among the best-covered. The
only thing between here and the cap is the open Lloros Awards incident (below).

---

## Since the May audit — what changed

The May 2026 audit scored the (then single-product) biwenger platform 9.4.
Two months of work turned the repo into a small product estate:

- **Be Water: 0 → v1.4 in seven weeks.** June README → public URL in 48 h,
  then productized across June–July on its **own GCP project**
  (`be-water-app`): open catalog of Spanish bottled waters, Firestore-backed,
  photo adds with Gemini label OCR, admin-gated AI photo studio (nano banana +
  watermark), similarity recommender, public community ranking + achievements.
  The July arc added real depth: the **official AESAN registry** (160
  recognised waters, parsed from the PDF, refresh script in-repo) driving the
  coverage mission bar and provenance autofill; **per-field provenance**
  (`✓ etiqueta` / `fabricante` / `a mano`) replacing the blanket "unverified"
  banner; **admin verification sign-off**; **catalog-curation tools**
  (fuzzy-duplicate + suspicious-value audits) and a **photo audit/repair**
  tool; a **monthly `catalog_sync` Cloud Run Job** reporting to Telegram; and a
  **Google Sign-In + admin flow shipped dormant**, waiting on one OAuth secret
  to flip to v2.0. ~44 fichas, OCU top-11 covered.
- **biwenger web kept growing** — season-agnostic **league calendar viewer**
  (month navigation, category colour-coding + filter, event detail modal) and
  **special-cup winner images on Palmarés**.
- **Cross-project CI** — one `deploy.yml` deploys both GCP projects via the
  shared WIF service account (keyless), per-module change detection; the
  cleanup job garbage-collects both Artifact Registry repos.
- **Cost model: strict €0 → sub-euro with hard caps.** The only paid call is
  the be_water studio photo (~$0.04, prepaid AI-Studio credits = impossible to
  overspend) plus Artifact Registry egress dust on deploy bursts. Guardrails:
  one €1 budget per project + one for Gemini, `scripts/check-gcp-costs.sh`
  audits both projects and the account-wide free tiers.
- **`chucknorris_bot`** keeps running unchanged; **`my_photos`** is a validated
  plan only (`packages/my_photos/README.md`), no code — blocked on user-side
  disk work.
- **Claude memory strategy inverted** — the memory directory is deliberately
  empty; durable knowledge lives in repo docs, skills and CLAUDE.md where any
  agent or human finds it.

### Open production incident (honest flag)

The **Lloros Awards** pages (biwenger web) render empty in prod: the Sheets
read throws `invalid_grant: Invalid JWT Signature` because the SA key backing
`biwenger-tools-sa-regional` was disabled during the Drive-cleanup /
SA-repoint work. Root-caused and fix documented in `PENDING.md`
(biwenger_tools); not yet applied. The daily-digest SLO is unaffected.

---

## Inventory — what is built

| Layer | Component | Stack / GCP |
|---|---|---|
| **HTTP services** | `biwenger-api` — Biwenger business logic over REST | Cloud Run · Flask + gunicorn · `--no-allow-unauthenticated` (OIDC) |
| | `biwenger-bot` — Telegram webhook → calls api | Cloud Run · Flask · webhook secret validation |
| | `biwenger-summary` — analytics web (tables, calendar, Palmarés, Awards) | Cloud Run · Flask · Tailwind CDN + vanilla JS |
| | `chucknorris-bot` — joke bot, resurrected 2015 side project | Cloud Run · Flask · `chucknorris.io` |
| | `be-water` — public waters catalog (project `be-water-app`) | Cloud Run · Flask · Firestore + GCS photos · Gemini OCR/studio |
| **Jobs / workers** | `biwenger-scraper-data` — weekly board scraper | Cloud Run Job · Sun 22:00 · BeautifulSoup + Biwenger SDK |
| | `be-water-catalog-sync` — monthly catalog reconcile → Telegram | Cloud Run Job · day 1 09:00 · reuses the `web` image with a command override |
| **Schedulers** | 3 Cloud Scheduler jobs (**at 3/3 account free-tier quota**) | daily digest `0 9 * * *`, weekly scraper, monthly catalog-sync — all `europe-west1` (Scheduler not offered in Madrid) |
| **Auto-bid engine** | `/market/auto-bid` + bot `/pujar` command | Tier table `min(price × multiplier, price + cap)` + jitter, Firestore idempotency, HTML-safe summary |
| **Lineup optimizer** | `/lineups/auto-pick` (+ `?dry_run=1`) | Memoised backtracking, captain MV cap, transient retry on Biwenger PUT |
| **Recommender** | `/budget/recommendations` (clausulazo targets) | `clause ≤ cash + dynamic margin`, sole-GK house rule |
| **Bot UX** | `/menu` inline keyboard + `/analizar` manager picker | Telegram callback_query dispatch |
| **Database** | Firestore native (`europe-southwest1`) ×2 projects | biwenger: `comunicados`, `participacion`, `clausulazos`, `tabla_justicia`, `palmares`, `auto_bid_log` (TTL 90d) · be-water: `waters`, `users` |
| | Composite index | `messages` by `categoria ASC + fecha DESC` |
| | TTL policy | `bids` collection-group via `expires_at` |
| **Sheets** | LIGAS_ESPECIALES + TROFEOS | Google Sheets API via SA mount (`biwenger-tools-sa-regional`) — **currently failing auth, see incident above** |
| **Object storage** | `be-water-photos` bucket (`us-central1` — deliberate: always-free tier is US-only) | Bottle photos, public read, EXIF stripped, 7-day tmp lifecycle |
| **Reference data** | AESAN registry (160 recognised waters) parsed from the official PDF | In-repo snapshot + refresh script; drives coverage + provenance autofill |
| **Secret management** | 6 JSON regional secrets across 2 projects (account free tier: 6/6) | biwenger: credentials, telegram-bot-config, chucknorris-bot-config, tools-sa, flask-web-config · be-water: flask-web-config (Flask + Telegram + Gemini, consolidated) |
| **Reverse-engineered APIs** | Biwenger `/api/v2/*` | DevTools capture, documented in SDK |
| | Jornada Perfecta `/api/fitness-daily` | Token via Frida + Android JS bundle (see `frida-android-intercept.md`) |
| **Build system** | Bazel + bzlmod + rules_python + rules_oci + rules_pkg | `python_service` macro, shared layers, hermetic |
| **Container registry** | Artifact Registry `biwenger-docker` + `be-water-docker` | Multi-arch `python-base` + per-service images; concurrency-gated cleanup post-deploy covers both repos |
| **CI/CD** | GitHub Actions `deploy.yml` | Detect changed → lint → test → per-module deploy (incl. cross-project `be-water` via WIF) → cleanup; `workflow_dispatch` fallback |
| **Lint / format** | flake8 + black (88 cols), hermetic via Bazel | CI gate before tests |
| **Tests** | pytest + requests-mock + MagicMock — 7 suites (core + 4 biwenger + chucknorris + be_water) | See _Test coverage_ below |
| **Domain models** | `LeagueMessage`, `Participation`, `Clausulazo`, `JusticeEntry`, `Palmares` (biwenger); `Water`, per-field provenance (be_water) | Symmetric `from_firestore` / `to_firestore` |
| **Image rendering** | Squad / market tables → PNG; be_water studio photos | matplotlib (biwenger) · Gemini image gen (be_water) |
| **Security** | webhook secret HMAC, OIDC service-to-service, ADC for Firestore, HTML sanitisation (bleach), CSRF tokens + per-IP rate limits (be_water), timing-safe admin login | Zero key files in the Firestore code path |
| **Cost controls** | €1 budget per project (+1 for Gemini), log retention 7d, `min-instances=0`, free-tier ceilings respected, AR cleanup script, prepaid Gemini credits (hard cap) | `scripts/check-gcp-costs.sh` audits both projects + account totals |
| **Observability** | Structured JSON logs via `core.utils.get_logger` | Cloud Logging only — alerts intentionally out of scope (see below) |
| **Documentation** | repo-wide `operations.md` + per-package `OPERATIONS.md`, `gcp.md`, `firestore.md` (both projects), `INFRA.md`, per-package DESIGN.md + release-notes, `frida-android-intercept.md` | Maintained, no orphan docs |
| **AI / agents** | `.claude/skills/`, `.claude/hooks/`, AGENTS.md; memory deliberately empty | Claude Code workflow integrated |
| **AI in product** | `core/sdk/gemini.py` — label OCR (free tier) + image generation (prepaid), retries on 429/503 | be_water photo-first add flow + admin studio |

---

## Test coverage

**Real line coverage is measured now** (`bazel coverage //...` — the
`rules_python` toolchain reported `LF:0` for every file until the 26-Jul
`configure_coverage_tool` fix; see `docs/operations.md`). Repo-wide: **80.2%**
(3510/4375 lines). The suite validates behaviour, not call patterns (regression
tests pinned to specific incidents, e.g. the 2026-05-24 HTML-escape silent
fail), and behaviour is now also written down as specs in `openspec/` (what
must be true) that each scenario links back to its test.

| Scope | line coverage | Note |
|---|---|---|
| biwenger scraper | 93% | highest |
| **be_water web** | **89%** | was the drag; the 26-Jul pass tested the photo pipeline (34→82%) + `recommend_nearby` |
| biwenger web | 81% | mature |
| core | 77% | SDK boundaries; rest is network I/O |
| chucknorris bot | 76% | small surface, fully behaviour-covered |
| biwenger api / bot | ~75% | load-bearing logic covered; uncovered is I/O + one-shot scripts |

Beyond line coverage, a **mutation-testing** pilot on the auto-bid engine
(259 mutants, ~70% killed after closing three real boundary gaps) confirms the
tests bite where it matters; the ad-hoc runbook is in `docs/operations.md`.
be_water's fast-shipped coverage debt — the honest reason the repo sat at 9.3 —
is paid.

---

## Strengths

1. **Multi-product without multiplying the machinery** — a second GCP project,
   a second product surface and a third cron rode the *same* Bazel macros, CI
   pipeline and cost model. Adding be_water cost almost no new infrastructure
   concepts; it reused `python_service`, WIF deploy, the cleanup job and the
   consolidated-secret pattern.
2. **CI/CD maturity** — per-module change detection, cross-project keyless
   (WIF) deploy, OIDC service-to-service, cleanup race fixed with a GH Actions
   `concurrency` group, `workflow_dispatch` as a manual safety net.
3. **Verifiable cost discipline** — sub-euro/month is real and hard-capped:
   free tiers respected on Secret Manager (6/6), Scheduler (3/3), Artifact
   Registry, Cloud Run and Firestore; the one paid API (Gemini image gen) runs
   on prepaid credits that cannot overspend. €1 budget alert per project.
4. **Idempotency by design** — SHA-256 doc IDs in the scraper, Firestore log
   keyed by `(date, player_id)` in auto-bid, provenance-aware upserts that
   never overwrite verified fields in be_water's monthly sync.
5. **Single-source-of-truth doctrine** — `CLAUDE.md` (charter), `openspec/`
   (behaviour contracts, per capability), `PENDING.md` (follow-ups), per-package
   `release-notes.md` (history), `INFRA.md` (GCP), this file (maturity). Claude
   memory deliberately empty. No duplication.
6. **Security hygiene** — webhook HMAC, OIDC bot↔api, regional secrets, ADC
   for Firestore (no key files in the request path), HTML sanitisation, plus
   be_water's public-facing armor (CSRF, per-IP rate limits, timing-safe admin
   login).
7. **Reverse engineering documented** — `frida-android-intercept.md` records
   how the JP token was captured; the Biwenger `/offers` endpoint was
   reverse-engineered from a live curl capture.

---

## Accepted gaps (intentional — they cap the score)

Improvements that would push above ~9.5 but were explicitly skipped to preserve
the project's constraints (single user, sub-euro/month, side-project scope):

| Gap | Why skipped | Score it would unlock |
|---|---|---|
| **Real observability** (Cloud Monitoring alerts, SLI dashboards, error-rate tracking) | Would push past the free tier; Cloud Logging is enough for a human-driven workflow | +0.20 |
| **Staging environment** | Local + prod is sufficient for one user; every merge deploys and the rollback path is fast | +0.15 |
| **Integration tests** against Firestore emulator / Biwenger sandbox | Heavy setup for low marginal value at this traffic | +0.15 |

Not counted as an accepted gap but real: **bus factor 1**. Every service, SDK
and runbook has a single author/operator. Fine for a side project, but it caps
how far "maturity" can honestly be claimed.

Total cap under the stated constraints: **~9.5 / 10**.

---

## Score progression

| Milestone | Score |
|---|---|
| Baseline (pre-Firestore, May 2026) | 7.5 |
| All biwenger PENDING follow-ups shipped (2026-05-24 audit) | 9.4 |
| Multi-product estate + be_water v1.4 (2026-07-25) | 9.3 |
| Quality-hardening pass — specs, real coverage, refactor (2026-07-26) | 9.4 |
| Theoretical max under current constraints | ~9.5 |

The 26-Jul pass recovered the coverage half of the earlier 9.4→9.3 dip:
behaviour specs across every package (`openspec/`), a fixed coverage gauge
(80% repo-wide, measured), the be_water photo-pipeline and `recommend_nearby`
tested, a mutation-tested auto-bid engine, and the 677-line be_water `app.py`
monolith split into a `routes/` package. What still separates the repo from the
~9.5 cap is the **open Lloros Awards incident** (Sheets JWT auth) plus the
intentional gaps below. Close the incident and it's at the cap.
