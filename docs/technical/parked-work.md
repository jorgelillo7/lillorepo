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

## Lloros Awards

Both Awards tabs render empty for 25-26. The Sheets read throws
`google.auth.exceptions.RefreshError: invalid_grant: Invalid JWT Signature`
*before* it ever touches the sheet — confirmed in `biwenger-summary` logs, with
the 25-26 sheet IDs correctly set and the sheets present.

The web service authenticates Sheets with
`biwenger-tools-sa@biwenger-tools.iam.gserviceaccount.com`, key
`78fe38d4a8101834a9b138f8e26ee966e1eef3f5`, mounted through the secret
`biwenger-tools-sa-regional:latest`. That key is its only user-managed one and
it is **disabled** — almost certainly during the Drive cleanup.

Three ways out:

- **(a)** Re-enable the key and redeploy to clear cached credentials. Two
  minutes, and keeps alive exactly the kind of key that caused this.
  ```bash
  gcloud iam service-accounts keys enable 78fe38d4a8101834a9b138f8e26ee966e1eef3f5 \
    --iam-account=biwenger-tools-sa@biwenger-tools.iam.gserviceaccount.com
  ```
- **(b)** Create a Sheets-only service account, share the sheets with it, new
  key → new secret version → redeploy, leaving the old key dead on purpose.
- **(c)** Move the awards into Firestore. Cheaper than it looks: Sheets now
  holds up **only** these pages — three `get_sheets_data` call sites in the
  whole repo — while comunicados, participación, clausulazos and the tabla all
  read Firestore. This drops the last Sheets dependency and the last
  user-managed SA key in the project, at the cost of a model and somewhere to
  edit the data.

**Blocked on a decision, not on the fix.** The league has not settled how the
awards are maintained during a season. (b) builds a service account that is
wasted if Sheets is dropped; (c) builds an editor that is wasted if a
spreadsheet was already the right tool. The natural moment to decide is when
the 26-27 sheets would have to be created anyway.

**Until that answer exists, do not touch that service account or its keys.**

## be_water country field

Add `country` to `Water`, defaulting to `"España"` — backward compatible, a
one-line migration in `catalog_sync`.

It unlocks the international waters people actually find in Spanish
supermarkets (Evian, Perrier, San Pellegrino…), a 🌍 achievement tier, and
country chips on the home page.

**Trigger:** the data verification pass finishing first. The recommender's
"places" and the province achievements both assume Spanish geography and need
a small rethink before a second country exists.
