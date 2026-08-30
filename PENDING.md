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
| 🔨 | `seed_data.py` holds six Lunares minerals a photographed label contradicts | The only thing `audit_data` still reports (`audit_photos` and the suspicious/duplicate checks are clean): bicarbonatos 340→290, cloruros 75→62,3, sulfatos 330→150, calcio 150→94,5, magnesio 50→40,7, sodio 55→38,9. Crosses `catalog_sync`'s verified-freeze, so not a blind edit |
| 👤 | Activate Google Sign-In and `/admin` | ~10 min of Console clicks · runbook in `packages/be_water/OPERATIONS.md` |
| ⏳ | `country` field on `Water` | The verification pass above · [analysis](docs/technical/parked-work.md#be_water-country-field) |
| ⏳ | A second, optional label photo for the origin panel | Enough waters with an empty spring · 3 of 5 bottles carry the manantial on a face the composition shot never sees · [why parked](docs/technical/parked-work.md#be_water--a-second-optional-label-photo) |
| ⏳ | `aquadeus` and `fuente-arquillo` may be one spring under two brands | Your eye: `find_duplicates` matches name tokens and these share none |
| 🔨 | Tailwind ships as the Play CDN script, no `defer` | Compiles styles in the browser on every load, on a mobile-first audience · needs a build step, not a one-line fix |
| 🔨 | Catalog thumbnails are CSS `background-image`, so they carry no `alt` | 47 of 48 waters earn nothing from image search and read as nothing to a screen reader · only the detail hero is a real `<img>` |
| 🔨 | No capability spec for auth/moderation, the add-water flow, or `label_ocr` | All three are live, tested code that no spec describes · [audit](openspec/specs/be_water/) |
