# Project status

Where `lillorepo` actually stands. Read this before believing any other doc's
claim about the project.

For the feature-by-feature story read `packages/*/release-notes.md`; for the
GCP inventory read `INFRA.md`; for open follow-ups read `PENDING.md`.

**Score: 9.35 / 10.** Cap under current constraints: **~9.5**.

Was 9.4, dropped to 9.2 on 2026-08-08 when an audit found a defect class that
had been there all along and was not being counted: **facts about Biwenger and
Jornada Perfecta transcribed into constants and never checked against the
source.** On 2026-08-09 most of that class was closed by actually asking the
providers — the league settings and the live JP payload answered nearly every
open question in two calls, and one dead branch was fixed. Back to 9.3; the
remaining 0.2 is the rollback gap, the open incident, and the handful of facts
still unconfirmed.

---

## The top — what is genuinely good

1. **Cost discipline that is enforced, not intended.** Sub-euro/month across
   two GCP projects, with €1 budget alarms, prepaid AI credits that cannot
   overspend, and a cost script auditing both projects' free tiers.
2. **Keyless deploys.** Workload Identity Federation end to end, including the
   cross-project be_water deploy. No service-account key exists to leak.
3. **One source of truth, and it holds.** The 2026-08-08 docs audit found
   **zero broken links across 49 documents**. Facts had drifted; structure had
   not.
4. **Behaviour specs wired to tests.** 22 specs, 129 scenarios, every one
   naming a test that exists — checked, not assumed.
5. **CI that reasons about the graph.** Pull requests run only the suites a
   change can break, derived from `rdeps` rather than a list that would rot;
   `master` always runs everything. A docs PR's test job: 89s → 21s.
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
- **Reverse-engineered APIs** — Biwenger `/api/v2/*` and Jornada Perfecta
  `fitness-daily` (token captured with Frida; see `docs/external/`).
- **Rendering** — squad and market tables to PNG (matplotlib); be_water studio
  photos (Gemini).
- **Security** — webhook HMAC, service-to-service OIDC, ADC for Firestore,
  HTML sanitisation, CSRF + per-IP rate limits on be_water. No key files in the
  Firestore path.

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
| Draft budget 50M with a 52M override | `DEFAULT_BUDGET` plus `BUDGET_OVERRIDES` — the Copa Castolo prize, as the reglamento says. Not a drift |

### Assumed — believed, never checked

| Assumption | Why it is shaky |
|---|---|
| **`nextMatch.status == "break"`** | The optimizer reads it as "no fixture this week" and scores 0. All 533 players currently report `pending`; `break` has never been observed, so neither the value nor the behaviour behind it is confirmed. |
| **The scoring conversion factors** | Measured once (0.225–0.610 by line) and frozen. They rescale a *projection* for a future matchday, which no formula can replace: the league's `customScore` needs match events, and a fixture that has not been played has none. Last season's real points are already computed from the formula in `fetch_real_points.py`. |
| **Biwenger's own `status` / `statusInfo`** | Never read; JP is the only source. Biwenger currently marks 24 injured, 11 doubt and 2 sanctioned with expected return dates, which would corroborate JP rather than replace it. |

---

## What lowers the score

| Problem | Cost |
|---|---|
| **Unverified provider facts** (table above). Three shipped defects: a legal pick rejected mid-draft, a legal XI declared impossible, and a status branch that never fired because JP spells it `sanctioned`, not `suspended`. All three were the code holding a rule the game does not have. The 2026-08-09 audit closed most of the class by reading the league settings and the live JP payload; what remains is narrower. | **−0.10** |
| **No revision rollback.** `clean-images-artifact.sh` keeps one digest per service, so the images older Cloud Run revisions point at are gone (verified: 96 `biwenger-api` revisions, 1 surviving image). Deliberate — free-tier headroom was preferred. Recovery from a bad deploy is revert + wait for CI, ~10 min. | **−0.10** |
| **Bus factor 1.** Every service, SDK and runbook has one author and one operator. Not fixable with engineering. | caps the rest |

### Accepted gaps — skipped on purpose, not oversights

| Gap | Why |
|---|---|
| Real observability (alerts, SLI dashboards) | Would leave the free tier; Cloud Logging suits a human-driven workflow |
| Staging environment | Local + prod is enough for one user |
| Integration tests against a Firestore emulator / Biwenger sandbox | Heavy setup for the marginal value at this traffic. A cheaper in-process bot↔api suite covers the contract that actually broke |
| Coverage for the draft skill's 32 tests | They live under `.claude/`, which coverage cannot instrument. The tests **do** run in CI; only the percentage misses them, and moving the code would blur the split between the skill's read-only scripts and the ones that write Firestore |

---

## Score progression

| Milestone | Score |
|---|---|
| Baseline (pre-Firestore, May 2026) | 7.5 |
| All biwenger follow-ups shipped (2026-05-24) | 9.4 |
| Multi-product estate + be_water v1.4 (2026-07-25) | 9.3 |
| Quality-hardening pass — specs, coverage, refactor (2026-07-26) | 9.4 |
| **Domain-constants audit (2026-08-08)** | **9.2** |
| Theoretical max under current constraints | ~9.5 |

The way back up is not more infrastructure — that part is done. It is
**verifying the domain model against the provider**: reading the statuses both
APIs already send, confirming the league rules held as constants, and putting a
check on the handful of facts a season can change underneath us.
