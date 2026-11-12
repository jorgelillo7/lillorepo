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
| ⏳ | Check the first weekly Firestore backups exist, in both projects | **Monday 16/11** (the schedule runs Sundays, first on 15/11) · `gcloud firestore backups list --location=europe-southwest1 --project=biwenger-tools` and the same for `be-water-app`; then drop this line · [setup](docs/firestore.md) |
| 🚧 | Reusable deploy workflow | A seventh service · [why parked](docs/technical/parked-work.md#reusable-deploy-workflow) |
| 🚧 | Per-service base images (`base_deps` from the lock) | Measured and parked again by the owner: modest gain, cold-start risk, Artifact Registry free tier · [numbers](docs/technical/parked-work.md#still-parked) |
| 🚧 | Distroless base image | Cold start eating the 07:15 SLO, or the free tier tightening · [measured](docs/technical/backend/container-strategy.md) · **further off since #540**: the amd64 base with bytecode halved the api's first request after a cold start (6.0–7.4 s → 3.3–3.7 s) |
| 🚧 | Containers run as root | The next change to how `core` reaches `/app` · [why parked](docs/technical/parked-work.md#containers-run-as-root) |
| 🔨 | Bump Pillow to 13 and certifi (and pyasn1, opentelemetry-api) in the lock, `docker/Dockerfile.base` and the base image digest: 30 Dependabot alerts wait on it | A session with Docker running and a `venv` holding `pip-tools` · steps in `.claude/skills/check-deps/UPGRADING.md`; the four majors on offer (gunicorn 27, Pillow 13, python-dateutil 4, soupsieve 4) touch nothing this repo calls, read from their changelogs · boot-test gunicorn 27 before it ships |
| 🔨 | Each of the two public services reads the whole `biwenger-secrets` bundle: split it into one secret per consumer (credentials for the api and the scraper, Telegram for whoever sends, the web's own) | A session, then your `terraform apply` and the three secret versions · it is the accepted gap in `STATUS.md` |
| 🔨 | `infra.yml` grants `id-token: write` to a workflow that pull requests trigger; the plan identity is read-only, so the exposure is that identity's viewer grants | Pick up: scope the permission to the job, or drop the pull-request trigger for forks |
| ⏳ | The deploy jobs authenticating with `id-token: write` granted per job | The next push that deploys a service · watch `deploy.yml` on it |

## core

| | What is missing | Waiting on |
|---|---|---|
| ⏳ | Move the Biwenger-only two thirds of `core` into its package | `core` becoming an obstacle — a Biwenger change that breaks another package. **The CI cost that looked like the trigger is gone**: it was the unused `core_deps`, not the file layout, and wiring the slices cut a `sdk/biwenger` edit from 10 suites to 5 · [measured](docs/technical/parked-work.md#the-shape-of-core) |

## biwenger_tools

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | A starter the squad cannot afford loses to a resale bid on the same morning (12/11: Sucic skipped for cash, Fran García bid as a riser): let auto-bid exceed the cash when the signing enters the eleven, the starter he displaces is worth the shortfall and the round is four days off or more; and keep the trader's cash when auto-bid skipped a starter for it | Parked with the other auto-bid changes · reverses the cash rule in `auto-bid`'s spec, so it starts as a proposal |
| 🚧 | Auto-bid and trader read the next 2–3 fixtures, not just the next match | Parked by the owner until the recent auto-bid changes settle · proposal: a hard run only lowers a bid (T3 cap) plus `prefer_easier` tie-break; reverses `team-analysis`'s "display only" decision, so it needs the spec changed with it |
| ⏳ | Is `LINEUP_SUB_STARTS_ABOVE` = 300 the right bar? | Promotions to read against real points. **Unblocked**: the projection ledger now stores both, automatically, so the record `log_promotions` could never produce exists. Still needs them to accumulate — one promotion in 12 months means this waits on seasons, not weeks · [how to read it](docs/technical/backend/projection-ledger.md) |
| ⏳ | Should the starts penalty be the draft's default? | Next pre-season, with both fifteens side by side · `--starts-penalty` exists and is off; on the Aspas case it drops him from 1st to 3rd (143 → 75) |
| ⏳ | What to do when JP and Biwenger disagree on availability | More sightings. **The first real one arrived 19/09**: Haitam, Biwenger `discarded` ("Asuntos incompatibles con la práctica deportiva") against JP's fieldable `other` — so the sensor works and the rate is what the 1-in-481 measurement predicted. One case is still not a rule; JP remains the only source a decision reads |
| ⏳ | `nextMatch.status == "break"` has never been observed | A break **while a lineup runs** · verified wired, 0 events · same ~20-row window: the sighting needs the status to land on a player I own |
| ⏳ | Re-measure the auto-bid shares (T1–T4) | More settled auctions — run `scripts/auto_bid/calibrate.py` monthly, **next ~late November** · 27/09 (137 auctions) set +40/+20/+10/+5 % for win rate; 12/10 (95 priced) cut them to +15/+8/+5/+3 % for value; 22/10 (196 priced) lifted T3/T4 to +6/+5 %, above the +0–5 % gap where most rival bids land · [how](packages/biwenger_tools/OPERATIONS.md) |
| ⏳ | Is 16 the right squad floor (`TRADER_MIN_SQUAD`, raised from 14 on 11/11)? | Late November with the trader's other checks: how often a reserve came on (`squad_gap.py` counts the substitutions), against what the two spare players lost in price while held |
| ⏳ | Was lowering `TRADER_HOLD_DAYS` from 14 to 7 right? (the keeper cover still reads the 14-day clause lock, `CLAUSE_LOCK_DAYS`) | Lowered on 9/11 on a selection-biased read of 148 league flips (sold within 7 days, 70–74 % up; held 10–21, 38–60 %) · check: simulate both holds on `price_snapshots`, late November, and the trader's own sales between day 7 and 14 · [measurements](docs/technical/backend/measurements.md) |
| ⏳ | Are two rounds missed (`TRADER_ABSENCE_ROUNDS`) and 6.4 M (`TRADER_STAR_PRICE`) the right lines for selling an absence? | Since 9/11 · each "baja larga" sale against the player's price when he came back, late November with the trader's other checks · [measurements](docs/technical/backend/measurements.md) |
| ⏳ | Does auto-bid's captain upgrade (the tier above for a player under 3 M who would captain better than the squad's best) pay? | Since 9/11 · late November with the auto-bid calibration: the upgraded signings, how often they captained, their points as captain · [measurements](docs/technical/backend/measurements.md) |
| ⏳ | Does the Oráculo blend beat Jornada Perfecta alone? (`ORACULO_W` stays, or goes to 0) — **until 9/11 it blended Oráculo's Diario AS points**; since then SofaScore for the ~40 listed players, JP alone for the rest, so grade rounds 13+ apart from the earlier ones | 10 rounds where the two elevens differ, graded by the projection ledger — 2 so far (J10 −9, J11 +3); it counted none until grading read the rounds the digest stores · read with `report.py`, [how](docs/technical/backend/projection-ledger.md) |
| ⏳ | What the squad is made of: why it scores below average while projected near the top | **Measured, rounds 1–11, all managers** (`scripts/projections/squad_gap.py`): the base SofaScore explains 19 of the 22 points a round to the leader, bonuses ~2; picking the eleven is at the league's average (72 % of hindsight, range 71–80 %); per million of team value the squad scores at the league's middle, but it is the cheapest (66 M against 72–110 M) and, with cash, the poorest manager (75 M against 89–140 M). **Where the wealth went**: market flips — −17.5 M for us (six August–September signings bought dear, −15.7 M) against +38–40 M for the two leaders; the trader's own flips since 22/10 are all up. Next: 8 rounds of `league_projection` · [`openspec/changes/squad-composition/`](openspec/changes/squad-composition/proposal.md) |
| ⏳ | Captain (and close defender calls) by the chance his team wins or keeps a clean sheet | 6–8 rounds of `team_outlook` in the projection ledger, captured from round 13 · free: Analítica Fantasy's calendar predictor, already the Oráculo source · expected gain is small (bonuses ~2 pts a round; captain tie-breaks ~0.5–1.5 by a review's estimate), so it ships only if the graded rounds show it · [what is stored](docs/technical/backend/projection-ledger.md) |
| ⏳ | Should a defender facing Barcelona or Real Madrid be benched whatever JP projects? | **Measured, the effect is real**: defenders score −3.3 (Barcelona) and −2.4 (Madrid) SofaScore points under their own mean, 9 and 10 of 11 games negative; keepers only against Barcelona. What decides a rule is whether JP already discounts it — 5 own-squad cases say no; `league_jp`, captured from round 13, gives the sample · `scripts/projections/opponent_effect.py`, [how to read it](docs/technical/backend/projection-ledger.md#the-opponent-effect) |

## my_photos

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Photo-recognition project | You: run the migration and free the disks · plan in `packages/my_photos/README.md` |
| 👤 | Photos, in the order that protects first: **(1)** the Google Photos app on both iPhones with backup at original quality — 5 TB are paid for and 10 GB used, so it is a second cloud for photos and videos with nothing to run; **(2)** copy, never move, the ten-year-old disk onto the 5 TB one, verify it, and upload that history too; **(3)** the `YYYY-MM-DD event` folders once or twice a year, with a script and a session proposing the names. Step 1 replaces Amazon Photos, rclone and emptying Google Photos | You for 1 and 2 (no code) · then a session rewrites `packages/my_photos/README.md`, in English, around this order: `icloudpd` is looking for maintainers and its Homebrew formula is deprecated, and rclone's shared Google Photos client ID is being retired during 2026 |

## group_polls

| | What is missing | Waiting on |
|---|---|---|
| 👤 | Create the Firebase project (Spark), then turn on `infra/group_polls.tf` and adopt it | You · **ready to run**: the runbook is reviewed against `infra/` (imports the default rules release too, App Check enforced last), and `ci_plan.tf` picks the project up by itself · `packages/group_polls/OPERATIONS.md` → "Create the project" |
| ⏳ | App Check enforcement for Firestore and Identity Toolkit declared in Terraform, and a per-user limit on creating polls | The Firebase project existing · today enforcement is a console click, and anonymous sign-in makes votes and polls free to mint |

## interactive_fiction

Next session starts here; the story-specific detail is in the local plan (`.claude/plans/interactive-fiction.md`, gitignored).

| | What is missing | Waiting on |
|---|---|---|
| ⏳ | Chapter 3 into the reader: art, scenes, SCARE among its valid codes, the condition/inventory setup | The author finishing it in `Capitulo 3/fuente/` on his `master` |
| 👤 | 3D draft of chapter 1: try [the preview](https://interactive-fiction-draft3d.jorgelillo.workers.dev) with the author and decide whether to continue (more rooms, full quality, then into the reader) | You and the author · [evaluation](docs/technical/parked-work.md#interactive_fiction--a-3d-draft-of-chapter-1) |
| ⏳ | Android app: wrap the site as a Trusted Web Activity (Bubblewrap; Google Play account US$25 once, content rating for horror/violence) — reuses the web as is | The 3D reader on the main URL (`openspec/changes/interactive-fiction-3d-reader`) |
| 🚧 | Publish on itch.io too (free, the genre's community, devlogs per chapter) | Parked by your call |
| 🔨 | Scene images as WebP or AVIF with `srcset`: 9.1 MB of JPEG/PNG today, 2.1 MB as WebP at 1600 px, 0.85 MB as AVIF at 1000 px (measured) | A decision on adding an encoder to the build (`sips` writes neither) |
| ⏳ | A custom domain and a save export code | Before the Android app or any promotion: saves live in the browser per origin, so a new URL loses them |
| 👤 | Suggestions for the author (speaker colours at 1.3:1 and 2.2:1 on black, the knife never shown, undo against the story's own rule, the 3D draft as a fixed-camera source instead of the reader) | You: forward the note or not · his content, not this repo's |

## wishlist

| | What is missing | Waiting on |
|---|---|---|
| 👤 | Gifts are added from `/admin` with a photo, and it is deployed: add one from an iPhone (the dialog, both photo buttons) and check the photo shows on the list | You · the browser side has no automated test, and no photo has been stored in the remote D1 yet (if the statement size limit refuses one, the fallback is the photo across several rows) |
| 🚧 | One list per event (birthdays), reached by an unguessable link | Your call · [`openspec/changes/wishlist-events/`](openspec/changes/wishlist-events/proposal.md) |

## be_water

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Activate Google Sign-In | ~10 min of Console clicks · **the studio photo is off for everyone until this is done** (it follows the Google-verified admin) · the ficha editor is built, tested and deployed behind a 404 until this is done · runbook in `packages/be_water/OPERATIONS.md` · **no code change needed**: be_water's CSP already allows Google Sign-In's script, style and frames (#542) |
| ⏳ | The AESAN parser reads only Spain's table, of 28 in the PDF | A registered foreign water · **checked:** it would not have caught `FONTÉBIL`, and Portugal's place column is `Locality-Municipality`, which `_PROVINCE` cannot read · [measurements](docs/technical/parked-work.md#be_water-country-field) |
| ⏳ | Tailwind ships as the Play CDN, which its own docs call development-only | A build step · **not** the `defer` this line used to ask for: deferring the compiler is what causes the unstyled flash · preconnect landed, the rest needs a Bazel node toolchain · affects `be_water` **and** `biwenger_tools/web` · **weighs more since #542**: the CDN compiles styles in the browser, which is the only reason both CSPs still allow `style-src 'unsafe-inline'` |
| 🔨 | `deploy.yml` still passes `BEWATER_ADMINS`, which nothing reads; `be-water` deploys with no `--max-instances` | Pick up with the next be_water change |
| 🔨 | The three `backfill_*` scripts, `audit_data.py` and `audit_photos.py` have no test importing them: delete the ones that have run for good, test the rest | Your call on which are finished |
| ⏳ | HEIC uploads are refused (JPEG, PNG and WebP only) | A contributor whose phone does not convert on upload · iOS Safari converts; not tried on a device |
