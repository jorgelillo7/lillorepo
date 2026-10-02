# Project status

Where `lillorepo` actually stands. Read this before believing any other doc's
claim about the project.

For the feature-by-feature story read `packages/*/release-notes.md`; for the
GCP inventory read `INFRA.md`; for open follow-ups read `PENDING.md`.

**Score: 9.35 / 10.** Cap under current constraints: **~9.5**.

The score is a reference point, not a target: the cap minus what is priced in
"What lowers the score", so it moves when a cost is found, paid or re-priced —
not when work ships. Work that removes a risk nobody had priced (the security
audit, the board archive) makes the project better without moving it.

Was 9.4, dropped to 9.2 on 2026-08-08 when an audit found a defect class that
had been there all along and was not being counted: **facts about Biwenger and
Jornada Perfecta transcribed into constants and never checked against the
source.** On 2026-08-09 most of that class was closed by actually asking the
providers — the league settings and the live JP payload answered nearly every
open question in two calls, and one dead branch was fixed: 9.3. Closing the
Lloros Awards incident on 2026-08-27 made it 9.35.

---

## The top — what is genuinely good

1. **Cost discipline that is enforced, not intended.** Sub-euro/month across
   two GCP projects, with €1 budget alarms, prepaid AI credits that cannot
   overspend, and a cost script auditing both projects' free tiers.
2. **Keyless deploys.** Workload Identity Federation end to end, including the
   cross-project be_water deploy. No key is involved in building or deploying;
   the one key left is runtime, the Sheets reader in `biwenger_tools/web`.
3. **One source of truth, and it holds.** The 2026-09-30 docs audit found
   **zero broken links across 56 documents**. Facts had drifted; structure had
   not.
4. **Behaviour specs wired to tests.** 40 specs, 364 scenarios, 1,072 test
   names cited and every one of them exists — checked, not assumed.
5. **CI that reasons about the graph.** Pull requests run only the suites a
   change can break, derived from `rdeps` rather than a list that would rot;
   `master` always runs everything. A docs PR's test job: 89s → 21s. Lint is
   one tool, Ruff (format, lint, import order), plus mypy over every package,
   in ~30–55 s where black and flake8 alone took 58–106 s; every PR's test job shows a coverage summary —
   78.5 % of the lines in tested files — and lists the files no test imports
   instead of hiding them.
6. **The draft, which is the hardest thing here.** A 105-pick snake draft
   arbitrated from Telegram, budget and composition validated per pick,
   multi-position players handled, squad shapes searched rather than assumed.
7. **Failures get written down.** The container strategy, the distroless
   decision and the absence of rollback are all recorded with their
   measurements and the trigger that would reopen them.

---

## What is built

Infrastructure inventory lives in `INFRA.md`; this is the capability list.

- **Services** — `biwenger-api` (business logic over REST, OIDC-only),
  `biwenger-bot` (Telegram webhook), `biwenger-summary` (analytics web),
  `chucknorris-bot`, `be-water` (own GCP project).
- **Jobs** — weekly league-board scraper, monthly be_water catalog sync.
- **Auto-bid engine** — tiered `min(price × multiplier, price + cap)` with
  jitter and Firestore idempotency.
- **Lineup optimizer** — memoised backtracking over 14 formations, captain MV
  cap, full bench, applied every morning at 09:00.
- **Draft** — 105-pick snake draft arbitrated from Telegram, per-pick budget
  and composition validation, plus an offline squad-shape search.
- **Recommender** — clausulazo targets under `clause ≤ cash + dynamic margin`.
- **League cash** — every manager's hidden balance rebuilt from the board for
  `/saldos`, backed by the scraper's append-only archive of the board's money
  entries, so what Biwenger forgets mid-season or purges at the season change
  still counts. Clausulazos are never deleted either.
- **Reverse-engineered APIs** — Biwenger `/api/v2/*` and Jornada Perfecta
  `fitness-daily` (token captured with Frida; see `docs/external/`).
- **Rendering** — squad and market tables to PNG (matplotlib); be_water studio
  photos (Gemini).
- **Security** — one service account per service with minimal grants (the
  default compute account holds no role), keyless deploys from `master` only
  with every action pinned to a commit, webhook HMAC, service-to-service OIDC,
  nonce-based CSP on both webs, CSRF, rate limits keyed on the real client IP,
  daily caps on Gemini, HTML sanitisation. No key files anywhere.

## What we know vs what we assume

The audit split the domain constants into facts verified against the provider
and facts merely believed. The second table is the useful one.

### Verified

| Fact | How |
|---|---|
| 14 formations (`FORMATIONS`) | Transcribed from the app's *Estrategia* picker, pinned by `test_formations_match_biwengers_strategy_picker` |
| Captain cap 3M is cf-base, not `owner.price` | Biwenger returned HTTP 403 on a real attempt |
| Positions 1–4 = GK/DEF/MID/FWD | Live competition payload |
| Position 5 = coaches, correctly excluded from the draft | Live payload (20 of them, 0 points); absent from the ranked CSV |
| Runtime deps match the production image | `scripts/check_base_sync.py`, every CI run |
| 25-player squad cap; 3M captain cap; multi-position on; coaches disabled; **no** team-value cap | League `settings` read live 2026-08-08: `teamMaxSize: 25`, `lineupCaptainMaxValue: 3`, `lineupMultiPos: true`, `lineupCoach: false`, `teamMaxValue: 0` |
| JP's status vocabulary | Live `fitness-daily`, 533 players: `ok`, `ok-available`, `injured`, `doubt`, `sanctioned`, `other`. The code tested for `suspended`, which JP never sends |
| Biwenger's own `status` is read, not ignored | `provider_watch` compares it with JP on every lineup run; the first disagreement was recorded on 2026-09-19 (Haitam: Biwenger `discarded`, JP a fieldable `other`) |
| Draft budget 50M with a 52M override | `DEFAULT_BUDGET` plus `BUDGET_OVERRIDES` — the Copa Castolo prize, as the reglamento says. Not a drift |

### Assumed — believed, never checked

| Assumption | Why it is shaky |
|---|---|
| **`nextMatch.status == "break"`** | The optimizer reads it as "no fixture this week" and scores 0. All 533 players currently report `pending`; `break` has never been observed, so neither the value nor the behaviour behind it is confirmed. |
| **The scoring conversion factors** | Measured once (0.225–0.610 by line) and frozen. They rescale a *projection* for a future matchday, which no formula can replace: the league's `customScore` needs match events, and a fixture that has not been played has none. Last season's real points are already computed from the formula in `fetch_real_points.py`. |

---

## What lowers the score

| Problem | Cost |
|---|---|
| **Unverified provider facts** (table above). Three shipped defects: a legal pick rejected mid-draft, a legal XI declared impossible, and a status branch that never fired because JP spells it `sanctioned`, not `suspended`. All three were the code holding a rule the game does not have. The 2026-08-09 audit closed most of the class by reading the league settings and the live JP payload, and Biwenger's statuses are now read and compared; what remains is the two assumptions above. | **−0.05** |
| **No revision rollback.** `clean-images-artifact.sh` keeps one digest per service, so the images older Cloud Run revisions point at are gone (verified: 96 `biwenger-api` revisions, 1 surviving image). Deliberate — free-tier headroom was preferred. Recovery from a bad deploy is revert + wait for CI, ~10 min. | **−0.10** |
| **Bus factor 1.** Every service, SDK and runbook has one author and one operator. Not fixable with engineering. | caps the rest |

### Accepted gaps — skipped on purpose, not oversights

| Gap | Why |
|---|---|
| One secret per package, not per service | `biwenger-secrets` holds the Biwenger password, the JP token, the bot and the web keys, so the bot and the web — the two public biwenger services — can read credentials they never use. Per-service accounts do not change this: the grant is on the secret, and the secret is one JSON. Traded for 3/6 free Secret Manager versions instead of 6/6, and one secret to rotate per package, on a private league with one operator |
| Real observability (alerts, SLI dashboards) | Would leave the free tier; Cloud Logging suits a human-driven workflow |
| Staging environment | Local + prod is enough for one user |
| Integration tests against a Firestore emulator / Biwenger sandbox | Heavy setup for the marginal value at this traffic. A cheaper in-process bot↔api suite covers the contract that actually broke |

---

## Score progression

| Milestone | Score |
|---|---|
| Baseline (pre-Firestore, May 2026) | 7.5 |
| All biwenger follow-ups shipped (2026-05-24) | 9.4 |
| Multi-product estate + be_water v1.4 (2026-07-25) | 9.3 |
| Quality-hardening pass — specs, coverage, refactor (2026-07-26) | 9.4 |
| Domain-constants audit (2026-08-08) | 9.2 |
| Providers asked directly — league settings, live JP (2026-08-09) | 9.3 |
| Lloros Awards incident closed (2026-08-27) | 9.35 |
| **Security audit, board archive; costs re-priced so the table adds up (2026-09-30)** | **9.35** |
| Theoretical max under current constraints | ~9.5 |

The way back up is not more infrastructure — that part is done. It is
**verifying the domain model against the provider**: reading the statuses both
APIs already send, confirming the league rules held as constants, and putting a
check on the handful of facts a season can change underneath us.
