# Pending work

The index of what is still open. **One line per item.** If it needs more than
that, the reasoning lives where it belongs and this file links to it:

- behaviour and decisions → `openspec/`
- technical evaluations and parked work → `docs/technical/parked-work.md`
- anything else → the PR that closed it, and `git log`

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
| 🚧 | Ruff · coverage in CI · gradual mypy · `base_deps` from the lock | One trigger each · [why parked](docs/technical/parked-work.md#still-parked) |
| 🚧 | Distroless base image | Cold start eating the 09:00 SLO, or the free tier tightening · [measured](docs/technical/backend/container-strategy.md) · **further off since #540**: the amd64 base with bytecode halved the api's first request after a cold start (6.0–7.4 s → 3.3–3.7 s) |
| 🚧 | Containers run as root | The next change to how `core` reaches `/app` · [why parked](docs/technical/parked-work.md#containers-run-as-root) |
| ⏳ | Bazel's Python is 3.14.4, the image's 3.14.7 | A `rules_python` release that maps 3.14.7 (2.3.4 and 2.4.0-rc0 stop at 3.14.4) · only the test/lint sandbox is behind; production already runs 3.14.7 · `check-deps` flags it |

## core

| | What is missing | Waiting on |
|---|---|---|
| ⏳ | Move the Biwenger-only two thirds of `core` into its package | `core` becoming an obstacle — a Biwenger change that breaks another package. **The CI cost that looked like the trigger is gone**: it was the unused `core_deps`, not the file layout, and wiring the slices cut a `sdk/biwenger` edit from 10 suites to 5 · [measured](docs/technical/parked-work.md#the-shape-of-core) |

## biwenger_tools

| | What is missing | Waiting on |
|---|---|---|
| ⏳ | Is `LINEUP_SUB_STARTS_ABOVE` = 300 the right bar? | Promotions to read against real points. **Unblocked**: the projection ledger now stores both, automatically, so the record `log_promotions` could never produce exists. Still needs them to accumulate — one promotion in 12 months means this waits on seasons, not weeks · [how to read it](docs/technical/backend/projection-ledger.md) |
| ⏳ | Should the starts penalty be the draft's default? | Next pre-season, with both fifteens side by side · `--starts-penalty` exists and is off; on the Aspas case it drops him from 1st to 3rd (143 → 75) |
| ⏳ | What to do when JP and Biwenger disagree on availability | More sightings. **The first real one arrived 19/09**: Haitam, Biwenger `discarded` ("Asuntos incompatibles con la práctica deportiva") against JP's fieldable `other` — so the sensor works and the rate is what the 1-in-481 measurement predicted. One case is still not a rule; JP remains the only source a decision reads |
| ⏳ | `nextMatch.status == "break"` has never been observed | A break **while a lineup runs** · verified wired, 0 events · same ~20-row window: the sighting needs the status to land on a player I own |
| ⏳ | Re-measure the auto-bid shares (T1–T4) | More settled auctions — run `scripts/auto_bid/calibrate.py` monthly, **next ~late October** · the first reading (137 auctions, 27/09) set +40/+20/+10/+5 %; the ≥ 10M band had only 9 · [how](packages/biwenger_tools/OPERATIONS.md) |

## my_photos

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Photo-recognition project | You: run the migration and free the disks · plan in `packages/my_photos/README.md` |

## be_water

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Activate Google Sign-In | ~10 min of Console clicks · the ficha editor is built, tested and deployed behind a 404 until this is done · runbook in `packages/be_water/OPERATIONS.md` · **no code change needed**: be_water's CSP already allows Google Sign-In's script, style and frames (#542) |
| ⏳ | The AESAN parser reads only Spain's table, of 28 in the PDF | A registered foreign water · **checked:** it would not have caught `FONTÉBIL`, and Portugal's place column is `Locality-Municipality`, which `_PROVINCE` cannot read · [measurements](docs/technical/parked-work.md#be_water-country-field) |
| ⏳ | Tailwind ships as the Play CDN, which its own docs call development-only | A build step · **not** the `defer` this line used to ask for: deferring the compiler is what causes the unstyled flash · preconnect landed, the rest needs a Bazel node toolchain · affects `be_water` **and** `biwenger_tools/web` · **weighs more since #542**: the CDN compiles styles in the browser, which is the only reason both CSPs still allow `style-src 'unsafe-inline'` |
