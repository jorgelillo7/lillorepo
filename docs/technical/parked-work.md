# Parked work

Why things in `PENDING.md` are not being done, and what would change that.

`PENDING.md` is the index: one line per item, scannable. This is where the
reasoning behind a parked line lives, so the index stays readable and the
reasoning stays recoverable. A parked item waits for a **trigger**, not for
boredom — each section below names its own.

---

## Reusable deploy workflow

Six near-identical ~90-line deploy blocks in `.github/workflows/deploy.yml`.

The duplication has already cost something real: `chucknorris_bot` was missing
from the cleanup script's `SIMPLE_IMAGES` and quietly accumulated 8 digests
before anyone noticed. So the case for consolidating is not aesthetic.

Against it: this is the riskiest refactor in the repo. The workflow is YAML,
untested, and its failures surface in production rather than in CI.

**Trigger:** a seventh service. Six is survivable; seven is where hand-editing
each block reliably drifts.

## Still parked

Each of these was reviewed and deliberately left alone.

**Ruff.** Lint already runs hermetically through Bazel — black and flake8 from
the lock, zero version drift, one entry point in `scripts/lint.sh`. Speed is
not a problem at this size. *Trigger:* flake8 blocking something real.

**Coverage in CI.** The Bazel + pytest-cov plumbing touches the lock and every
test target, which outweighs the visibility. Worth noting what coverage would
*not* have caught: `/comparar` was written and unwired, and the dead
`suspended` branch **was** executed by tests, with a value the provider never
sends. *Trigger:* a shipped regression that coverage would genuinely have
caught.

**Gradual mypy.** *Trigger:* the day a type bug actually bites.

**Parametrised `base_deps` / `Dockerfile.base` from the lock.** Build-system
surgery, and further away since the sync guard now catches the drift this
would have prevented, at a fraction of the risk. *Trigger:* a package whose
dependencies materially diverge from the base image.

Related: `core_deps` on `service(…)` exists and lets a package link only the
slices of `//core` it uses, but it cannot shrink an image while
`Dockerfile.base` installs every dependency and all six images share one base.
The size win needs both this item and per-service bases.

## The shape of `core`

Measured across the repo, excluding tests:

| Module | Lines | Consumers |
|---|---:|---|
| `sdk/telegram` | 426 | be_water · biwenger_tools · chucknorris_bot |
| `sdk/firestore` | 177 | be_water · biwenger_tools |
| `web/csrf` + `web/ratelimit` | 67 | be_water · biwenger_tools |
| `utils` | 60 | all three |
| `sdk/http` | 109 | core itself · biwenger_tools |
| `sdk/biwenger` | 824 | biwenger_tools only |
| `domain/models` | 364 | biwenger_tools only |
| `sdk/jp` | 203 | biwenger_tools only |
| `sdk/gcp` | 99 | biwenger_tools only |
| `sdk/gemini` | 168 | be_water only |

Genuinely shared: ~730 lines. Single-consumer: ~1,718.

This is expiry rather than a design error: `core` grew when `web` and
`scraper_job` started sharing Biwenger code, which was correct then, and the
split into packages left the rest stranded. The league constants have already
moved out — they were riding into every other service's image through `_init`.

The rest stays. It is a large refactor with no runtime gain, and the README has
defined `core` this way since before there were other packages.

**Triggers:** a second package needing a domain-model layer, or a package that
wants none of the Biwenger SDK and has to justify carrying it.

## Lloros Awards → Competiciones

**Decided and shipped.** The league kept Sheets, chose option (a), and the key
`78fe38d4…` on `biwenger-tools-sa` was re-enabled on 2026-08-27. Both pages had
rendered empty for a season because that key was disabled — almost certainly
during the Drive cleanup — so every read threw
`google.auth.exceptions.RefreshError: invalid_grant` before touching a sheet.

The page went further than the fix. It is now **Competiciones**, and the
spreadsheet decides what it holds: configuration keeps one entry per season
listing workbook ids, and each tab classifies itself (`Jornada | Partido` is
the Liga H2H fixture block, `Nombre de la liga` in A1 is a table). Adding or
retiring a competition is adding or deleting a tab. The old shape — one sheet
id per competition per season, each needing a code edit, a GitHub secret and a
deploy — is what left the pages dark for a year.

**Option (b), a Sheets-only service account, was declined.** The web keeps
authenticating with `biwenger-tools-sa`. The reasoning is in `STATUS.md` under
"Accepted gaps": it would buy a narrower blast radius on a single-operator
private league, and cost a new key, a Secret Manager version the billing
account does not have spare (it sits at exactly 6 of 6 free), and a second
credential to remember at every rollover.

The workbooks are **Restricted**, shared with the Sheets service account and
nobody else with a link. They were briefly link-public while the ids were being
read during design; that was undone on 2026-08-28 and the reads were verified
against the closed sheets, so option (c') — dropping the credential and reading
a published CSV — is no longer available and would mean making league data
public again to get it back.

Option (c), moving the awards into Firestore, is now the *wrong* trade: the
league edits these tables weekly in a spreadsheet and wants to keep doing so.
What (c) was really solving — configuration that needs a deploy — is better
solved by moving the workbook ids into Firestore and editing them from
`/admin`, which leaves the data where its editors are.

## be_water country field

Add `country` to `Water`, defaulting to `"España"` — backward compatible, a
one-line migration in `catalog_sync`.

It unlocks the international waters people actually find in Spanish
supermarkets (Evian, Perrier, San Pellegrino…), a 🌍 achievement tier, and
country chips on the home page.

**Trigger:** the data verification pass finishing first. The recommender's
"places" and the province achievements both assume Spanish geography and need
a small rethink before a second country exists.

## be_water — a second, optional label photo

The composition panel and the origin panel are rarely the same piece of
label. Of five bottles photographed in one sitting, **three** carried the
spring and its municipality on a face the composition shot never sees:

| Water | On the other panel |
|---|---|
| `22` | Manantial de Peñaclara · Torrecilla en Cameros (La Rioja) |
| `sierra-natura` | Manantial Natura · Finca La Pandera · Los Villares (Jaén) |
| `lunares` | Manantial Lunares · Jaraba (Zaragoza) |

For `sierra-natura` that panel was the **only** source of the one thing its
ficha lacked, and the official registry could not have supplied it — see the
`_prefill_from_aesan` comment for why it would have supplied the wrong
province instead.

What it would look like: not a third fixed upload, but a prompt that appears
only when `spring` or `province` comes back empty from the OCR pass — today
that is 1 ficha in 46, so the form does not get heavier for everyone. The
extraction is the same shape as the mineral one, and the fields already have
their vocabulary and validation (`geo.ALL_PROVINCES`, `submission.resolve_place`,
the AESAN cross-check).

It would also close a gap in the provenance vocabulary: `label` (✓ etiqueta)
can only be earned by a mineral today. Identity can be `aesan` or `manual`
and never "confirmed from a photograph", even when a photograph is exactly
what proves it.

**Cost:** a second Gemini call per submission, and a third object per water in
the bucket.

**Trigger:** enough waters with an empty spring to be worth it, or the first
time a contributor gets the province wrong in a way the registry cannot catch.
One ficha does not justify it; the repair script that fixed `sierra-natura` by
hand was cheaper.
