# Pending work

The index of what is still open. **One line per item.** If it needs more than
that, the reasoning lives where it belongs and this file links to it:

- behaviour and decisions → `openspec/`
- technical evaluations and parked work → `docs/technical/parked-work.md`
- anything else → the PR that closed it, and `git log`

What each `biwenger_tools` measurement asks, what it has found and what would
change the code: [`docs/technical/backend/measurements.md`](docs/technical/backend/measurements.md).

Never deleted; lines are pruned as items ship. Grouped by area, `infra` being
the cross-cutting GCP/CI/policy one. What has **shipped** lives in
`packages/biwenger_tools/release-notes.md`, and the current state of the repo
in `STATUS.md` — neither belongs here.

**👤 needs you** · **⏳ waiting on a trigger or on data** · **🔨 ready to pick up** ·
**🚧 blocked on you, and parked by your call** — not up for planning until you unblock it

---

## infra

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Reusable deploy workflow | A seventh service · [why parked](docs/technical/parked-work.md#reusable-deploy-workflow) |
| 🚧 | Per-service base images (`base_deps` from the lock) | Measured and parked again by the owner: modest gain, cold-start risk, Artifact Registry free tier · [numbers](docs/technical/parked-work.md#still-parked) |
| 🚧 | Distroless base image | Cold start eating the 07:15 SLO, or the free tier tightening · [measured](docs/technical/backend/container-strategy.md) · **further off since #540**: the amd64 base with bytecode halved the api's first request after a cold start (6.0–7.4 s → 3.3–3.7 s) |
| 🚧 | Containers run as root | The next change to how `core` reaches `/app` · [why parked](docs/technical/parked-work.md#containers-run-as-root) |

## core

| | What is missing | Waiting on |
|---|---|---|
| ⏳ | Move the Biwenger-only two thirds of `core` into its package | `core` becoming an obstacle — a Biwenger change that breaks another package. **The CI cost that looked like the trigger is gone**: it was the unused `core_deps`, not the file layout, and wiring the slices cut a `sdk/biwenger` edit from 10 suites to 5 · [measured](docs/technical/parked-work.md#the-shape-of-core) |

## biwenger_tools

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Auto-bid and trader read the next 2–3 fixtures, not just the next match | Parked by the owner until the recent auto-bid changes settle · proposal: a hard run only lowers a bid (T3 cap) plus `prefer_easier` tie-break; reverses `team-analysis`'s "display only" decision, so it needs the spec changed with it |
| ⏳ | Is `LINEUP_SUB_STARTS_ABOVE` = 300 the right bar? | Promotions to read against real points. **Unblocked**: the projection ledger now stores both, automatically, so the record `log_promotions` could never produce exists. Still needs them to accumulate — one promotion in 12 months means this waits on seasons, not weeks · [how to read it](docs/technical/backend/projection-ledger.md) |
| ⏳ | Should the starts penalty be the draft's default? | Next pre-season, with both fifteens side by side · `--starts-penalty` exists and is off; on the Aspas case it drops him from 1st to 3rd (143 → 75) |
| ⏳ | What to do when JP and Biwenger disagree on availability | More sightings. **The first real one arrived 19/09**: Haitam, Biwenger `discarded` ("Asuntos incompatibles con la práctica deportiva") against JP's fieldable `other` — so the sensor works and the rate is what the 1-in-481 measurement predicted. One case is still not a rule; JP remains the only source a decision reads |
| ⏳ | `nextMatch.status == "break"` has never been observed | A break **while a lineup runs** · verified wired, 0 events · same ~20-row window: the sighting needs the status to land on a player I own |
| ⏳ | Re-measure the auto-bid shares (T1–T4) | More settled auctions — run `scripts/auto_bid/calibrate.py` monthly, **next ~late November** · 27/09 (137 auctions) set +40/+20/+10/+5 % for win rate; 12/10 (95 priced) cut them to +15/+8/+5/+3 % for value; 22/10 (196 priced) lifted T3/T4 to +6/+5 %, above the +0–5 % gap where most rival bids land · [how](packages/biwenger_tools/OPERATIONS.md) |
| ⏳ | Is `TRADER_HOLD_DAYS` = 14 too long? (a signing is never sold in its first two weeks, matching Biwenger's clause lock) | **First read on 148 league flips** (`board_archive`): sold within 7 days, 70–74 % were up; held 10–21 days, 38–60 %, and the most profitable manager holds ~10 days. Selection-biased (sellers chose when), so it argues for a profit-taking exception, not a verdict · next: simulate on `price_snapshots`, late November · [measurements](docs/technical/backend/measurements.md) |
| ⏳ | Does the Oráculo blend beat Jornada Perfecta alone? (`ORACULO_W` stays, or goes to 0) | 10 rounds where the two elevens differ, graded by the projection ledger — 2 so far (J10 −9, J11 +3); it counted none until grading read the rounds the digest stores · read with `report.py`, [how](docs/technical/backend/projection-ledger.md) |
| ⏳ | What the squad is made of: why it scores below average while projected near the top | **Measured, rounds 1–11, all managers** (`scripts/projections/squad_gap.py`): the base SofaScore explains 19 of the 22 points a round to the leader, bonuses ~2; picking the eleven is at the league's average (72 % of hindsight, range 71–80 %); per million of team value the squad scores at the league's middle, but it is the cheapest (66 M against 72–110 M) and, with cash, the poorest manager (75 M against 89–140 M). **Where the wealth went**: market flips — −17.5 M for us (six August–September signings bought dear, −15.7 M) against +38–40 M for the two leaders; the trader's own flips since 22/10 are all up. Next: 8 rounds of `league_projection` · [`openspec/changes/squad-composition/`](openspec/changes/squad-composition/proposal.md) |
| ⏳ | Captain (and close defender calls) by the chance his team wins or keeps a clean sheet | 6–8 rounds of `team_outlook` in the projection ledger, captured from round 13 · free: Analítica Fantasy's calendar predictor, already the Oráculo source · expected gain is small (bonuses ~2 pts a round; captain tie-breaks ~0.5–1.5 by a review's estimate), so it ships only if the graded rounds show it · [what is stored](docs/technical/backend/projection-ledger.md) |
| ⏳ | Oráculo's points on the predictions page and in its API (`sistema=biwenger-sofascore`) disagree, and not by a constant; the blend reads the page | A few graded rounds of `oraculo_scales`, stored with every projection from round 13 (~40 players a round) · then: which tracks Biwenger's points, and whether the blend's order changes with it |
| ⏳ | Should a defender facing Barcelona or Real Madrid be benched whatever JP projects? | **Measured, the effect is real**: defenders score −3.3 (Barcelona) and −2.4 (Madrid) SofaScore points under their own mean, 9 and 10 of 11 games negative; keepers only against Barcelona. What decides a rule is whether JP already discounts it — 5 own-squad cases say no; `league_jp`, captured from round 13, gives the sample · `scripts/projections/opponent_effect.py`, [how to read it](docs/technical/backend/projection-ledger.md#the-opponent-effect) |

## my_photos

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Photo-recognition project | You: run the migration and free the disks · plan in `packages/my_photos/README.md` |

## group_polls

| | What is missing | Waiting on |
|---|---|---|
| 👤 | Create the Firebase project (Spark), then turn on `infra/group_polls.tf` and adopt it | You · **ready to run**: the runbook is reviewed against `infra/` (imports the default rules release too, App Check enforced last), and `ci_plan.tf` picks the project up by itself · `packages/group_polls/OPERATIONS.md` → "Create the project" |

## interactive_fiction

Next session starts here; the story-specific detail is in the local plan (`.claude/plans/interactive-fiction.md`, gitignored).

| | What is missing | Waiting on |
|---|---|---|
| ⏳ | Chapter 3 into the reader: art, scenes, SCARE among its valid codes, the condition/inventory setup | The author finishing it in `Capitulo 3/fuente/` on his `master` |
| 👤 | 3D draft of chapter 1: try [the preview](https://interactive-fiction-draft3d.jorgelillo.workers.dev) with the author and decide whether to continue (more rooms, full quality, then into the reader) | You and the author · [evaluation](docs/technical/parked-work.md#interactive_fiction--a-3d-draft-of-chapter-1) |
| ⏳ | Android app: wrap the site as a Trusted Web Activity (Bubblewrap; Google Play account US$25 once, content rating for horror/violence) — reuses the web as is | The 3D reader on the main URL (`openspec/changes/interactive-fiction-3d-reader`) |
| 🚧 | Publish on itch.io too (free, the genre's community, devlogs per chapter) | Parked by your call |

## be_water

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Activate Google Sign-In | ~10 min of Console clicks · the ficha editor is built, tested and deployed behind a 404 until this is done · runbook in `packages/be_water/OPERATIONS.md` · **no code change needed**: be_water's CSP already allows Google Sign-In's script, style and frames (#542) |
| ⏳ | The AESAN parser reads only Spain's table, of 28 in the PDF | A registered foreign water · **checked:** it would not have caught `FONTÉBIL`, and Portugal's place column is `Locality-Municipality`, which `_PROVINCE` cannot read · [measurements](docs/technical/parked-work.md#be_water-country-field) |
| ⏳ | Tailwind ships as the Play CDN, which its own docs call development-only | A build step · **not** the `defer` this line used to ask for: deferring the compiler is what causes the unstyled flash · preconnect landed, the rest needs a Bazel node toolchain · affects `be_water` **and** `biwenger_tools/web` · **weighs more since #542**: the CDN compiles styles in the browser, which is the only reason both CSPs still allow `style-src 'unsafe-inline'` |
