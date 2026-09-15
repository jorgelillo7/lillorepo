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

**👤 needs you** · **⏳ waiting on a trigger or on data** · **🔨 ready to pick up**

---

## infra

| | What is missing | Waiting on |
|---|---|---|
| ⏳ | Reusable deploy workflow | A seventh service · [why parked](docs/technical/parked-work.md#reusable-deploy-workflow) |
| ⏳ | Ruff · coverage in CI · gradual mypy · `base_deps` from the lock | One trigger each · [why parked](docs/technical/parked-work.md#still-parked) |
| ⏳ | Distroless base image | Cold start eating the 09:00 SLO, or the free tier tightening · [measured](docs/technical/backend/container-strategy.md) |

## core

| | What is missing | Waiting on |
|---|---|---|
| 👤 | `decide_offer`: wrap it in the retry helper, or not? | One repeated PUT on the next real offer · [analysis](openspec/specs/core/biwenger-writes/spec.md) |
| ⏳ | Move the Biwenger-only two thirds of `core` into its package | A second package needing a domain-model layer · [numbers](docs/technical/parked-work.md#the-shape-of-core) |

## biwenger_tools

| | What is missing | Waiting on |
|---|---|---|
| 🔨 | A second projection source beside Jornada Perfecta | **Next: a capture with the projections screen open.** First capture found `server.analiticafantasy.com` (Oráculo is the tool inside it) with 3 endpoints, cookie auth, but **no player/projection endpoint** — the host is confirmed, the read is not · this is the "improve the projection logic" item · [capture + plan](docs/technical/backend/second-projection-source.md) |
| 🔨 | Nothing records what was projected against what was scored | Worth doing whether or not a second source ever arrives — without it "is JP worth it" has no answer · [why](docs/technical/backend/second-projection-source.md) |
| 👤 | The Liga H2H champion has no palmarés slot | You: art. 3.5 proclaims one, `SPECIAL_TOURNAMENTS` has no slug and it would need a graphic · decided at the first H2H rollover |
| ⏳ | `Lucen`/`Lillo`/`Rubén` in the sheets vs `Lucena`/`Jorge`/`Ruben` in `LEAGUE_MEMBERS` | Harmless today · becomes load-bearing when art. 3.5 puts the H2H champion in the palmarés and art. 3.6 makes H2H the league tiebreak |
| ⏳ | Is `LINEUP_SUB_STARTS_ABOVE` = 350 the right bar? | A few rounds of `log_promotions` read against real points |
| 👤 | The draft optimiser buys a cameo total at full value | You: `build()` ranks on raw `sf` with no starts penalty, so 143 points off 32 substitute appearances outbids a regular. `is_starter` only orders `_xi` and prints 🪑. Changing it moves which 15 get drafted |
| ⏳ | What to do when JP and Biwenger disagree on availability | A season of `provider_watch` disagreements to count |
| ⏳ | `nextMatch.status == "break"` has never been observed | The first international break — `provider_watch` logs the sighting |

## my_photos

| | What is missing | Waiting on |
|---|---|---|
| 👤 | Photo-recognition project | You: run the migration and free the disks · plan in `packages/my_photos/README.md` |

## be_water

| | What is missing | Waiting on |
|---|---|---|
| 👤 | Activate Google Sign-In and `/admin` | ~10 min of Console clicks · blocks every admin item below, `/admin` 404s without it · runbook in `packages/be_water/OPERATIONS.md` |
| 🔨 | `/admin` cannot edit a ficha — a missing province or community needs the CLI | Sign-In above · 2 fichas of 51 need it today · the engine exists (`data_audit`, `save_revision`), it needs a form with selects · [what to reuse](docs/technical/parked-work.md#be_water--repairing-a-ficha-from-the-admin-page) |
| ⏳ | The AESAN parser reads only Spain's table, of 28 in the PDF | A registered foreign water · **checked:** it would not have caught `FONTÉBIL`, and Portugal's place column is `Locality-Municipality`, which `_PROVINCE` cannot read · [measurements](docs/technical/parked-work.md#be_water-country-field) |
| 🔨 | A third, optional photo: the identity panel nobody photographs | Nothing: **the trigger fired** · the form takes 2 photos and reads 1 — the pretty front is never OCR'd · `fuente-dehesa` hit `verified=True` with no origin · [what's on it](docs/technical/parked-work.md#be_water--the-third-photo-and-the-identity-on-it) |
| 🔨 | The RGSEAA number and the bottler are on no ficha | Nothing · identity matching is fuzzy name overlap today · a registry number is unambiguous, and the bottler is what links two supermarket own-brands · same panel as above |
| 🔨 | The optional `beauty` photo is uploaded and never read | Nothing · it is already in hand and already paid for; the OCR only ever sees the composition shot |
| 🔨 | Tailwind ships as the Play CDN script, no `defer` | Compiles styles in the browser on every load, on a mobile-first audience · needs a build step, not a one-line fix |
