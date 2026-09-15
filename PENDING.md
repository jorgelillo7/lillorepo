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
| 🚧 | Distroless base image | Cold start eating the 09:00 SLO, or the free tier tightening · [measured](docs/technical/backend/container-strategy.md) |

## core

| | What is missing | Waiting on |
|---|---|---|
| ⏳ | Move the Biwenger-only two thirds of `core` into its package | `core` becoming an obstacle — **not** the old trigger, which can no longer fire: `be_water` arrived and wrote its own `domain.py` without touching `core` · [numbers](docs/technical/parked-work.md#the-shape-of-core) |

## biwenger_tools

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | A second projection source beside Jornada Perfecta (Oráculo / Analítica Fantasy) | You: the next step is a browser capture with the projections screen open · plan and first capture in [PR #417](https://github.com/jorgelillo7/lillorepo/pull/417), which stays open |
| 👤 | The Liga H2H champion has no palmarés slot | You: art. 3.5 proclaims one, `SPECIAL_TOURNAMENTS` has no slug and it would need a graphic · decided at the first H2H rollover |
| ⏳ | `Lucen`/`Lillo`/`Rubén` in the sheets vs `Lucena`/`Jorge`/`Ruben` in `LEAGUE_MEMBERS` | Harmless today · becomes load-bearing when art. 3.5 puts the H2H champion in the palmarés and art. 3.6 makes H2H the league tiebreak |
| ⏳ | Is `LINEUP_SUB_STARTS_ABOVE` = 300 the right bar? | More promotions to read against real points · **one in 12 months:** Valverde (328) displaced Giuliano Simeone on 2026-09-09, which 350 would have prevented · `log_promotions` records the bet but not what either scored, so grading it needs that first |
| 👤 | The draft optimiser buys a cameo total at full value | You: `build()` ranks on raw `sf` with no starts penalty, so 143 points off 32 substitute appearances outbids a regular. `is_starter` only orders `_xi` and prints 🪑. Changing it moves which 15 get drafted |
| ⏳ | What to do when JP and Biwenger disagree on availability | Far more than a season · **verified wired, 0 events in 12 months** · the 1-in-481 baseline was measured league-wide but `observe()` only sees my ~20 squad rows, so ≈1 expected per 24 lineups |
| ⏳ | `nextMatch.status == "break"` has never been observed | A break **while a lineup runs** · verified wired, 0 events · same ~20-row window: the sighting needs the status to land on a player I own |

## my_photos

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Photo-recognition project | You: run the migration and free the disks · plan in `packages/my_photos/README.md` |

## be_water

| | What is missing | Waiting on |
|---|---|---|
| 🚧 | Activate Google Sign-In | ~10 min of Console clicks · the ficha editor is built, tested and deployed behind a 404 until this is done · runbook in `packages/be_water/OPERATIONS.md` |
| ⏳ | The AESAN parser reads only Spain's table, of 28 in the PDF | A registered foreign water · **checked:** it would not have caught `FONTÉBIL`, and Portugal's place column is `Locality-Municipality`, which `_PROVINCE` cannot read · [measurements](docs/technical/parked-work.md#be_water-country-field) |
| ⏳ | Tailwind ships as the Play CDN, which its own docs call development-only | A build step · **not** the `defer` this line used to ask for: deferring the compiler is what causes the unstyled flash · preconnect landed, the rest needs a Bazel node toolchain · affects `be_water` **and** `biwenger_tools/web` |
