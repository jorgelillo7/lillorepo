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
| 👤 | Repoint `biwenger-tools-sa-regional` to a Sheets-only SA | The Awards decision below — **do not touch that SA or its keys until it exists** |
| 🔨 | Stacked PRs get no CI here, and merging their base closes them | Widening `ci.yml`'s trigger, or always branching off `master` |
| ⏳ | Reusable deploy workflow | A seventh service · [why parked](docs/technical/parked-work.md#reusable-deploy-workflow) |
| ⏳ | Ruff · coverage in CI · gradual mypy · `base_deps` from the lock | One trigger each · [why parked](docs/technical/parked-work.md#still-parked) |
| ⏳ | Distroless base image | Cold start eating the 09:00 SLO, or the free tier tightening · [measured](docs/technical/backend/container-strategy.md) |

## core

| | What is missing | Waiting on |
|---|---|---|
| 👤 | `decide_offer`: wrap it in the retry helper, or not? | One repeated PUT on the next real offer · [analysis](openspec/specs/core/biwenger-writes/spec.md) |
| 🔨 | Read-path test gaps in the Biwenger SDK | Nothing — the GAP blocks in `openspec/specs/core/biwenger-reads/spec.md` are the list |
| ⏳ | Move the Biwenger-only two thirds of `core` into its package | A second package needing a domain-model layer · [numbers](docs/technical/parked-work.md#the-shape-of-core) |

## biwenger_tools

| | What is missing | Waiting on |
|---|---|---|
| 👤 | Lloros Awards render empty for 25-26 | The league settling how awards get maintained · [root cause and options](docs/technical/parked-work.md#lloros-awards) |
| 👤 | Season 26-27 award sheets | You creating them and sharing the IDs |
| 🔨 | Formation ties are settled by `FORMATIONS` list order, which has no meaning | A tiebreaker with a reason behind it |
| ⏳ | Is `LINEUP_SUB_STARTS_ABOVE` = 350 the right bar? | A few rounds of `log_promotions` read against real points |
| ⏳ | What to do when JP and Biwenger disagree on availability | A season of `provider_watch` disagreements to count |
| ⏳ | `nextMatch.status == "break"` has never been observed | The first international break — `provider_watch` logs the sighting |

## my_photos

| | What is missing | Waiting on |
|---|---|---|
| 👤 | Photo-recognition project | You: run the migration and free the disks · plan in `packages/my_photos/README.md` |

## be_water

| | What is missing | Waiting on |
|---|---|---|
| 👤 | `audit_photos --fix` (2 fichas) and `audit_data` (5 fichas) | You: both prompt before every write, local via ADC |
| 👤 | Activate Google Sign-In and `/admin` | ~10 min of Console clicks · runbook in `packages/be_water/OPERATIONS.md` |
| ⏳ | `country` field on `Water` | The verification pass above · [analysis](docs/technical/parked-work.md#be_water-country-field) |
| ⏳ | Refresh the AESAN snapshot every few months | `packages/be_water/scripts/refresh_aesan_snapshot.py` — a git diff means new waters |
