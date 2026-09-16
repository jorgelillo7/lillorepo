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

**The trigger as written can no longer fire.** It said "a second package needing a domain-model layer". `be_water` is that second package, and it
wrote its own `domain.py` without importing anything from `core/domain` —
which is the answer, not the wait: a package that needs a domain model
writes the one it needs. So the trigger is now `core` becoming an obstacle,
i.e. a change made for Biwenger that breaks another package.

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

`Water.country` exists and defaults to `"ES"` (`domain.py`), but nothing writes
it, nothing reads it and no form offers it. Every water in the catalog is
therefore Spanish by assertion, not by evidence.

**The trigger has fired, and the stored document is worse than "no country".**
`FONTÉBIL` (Mercadona, 1 L) is bottled by Outeirinho Turismo Indústria S.A. in
Fafe, **Portugal**. Its ficha reads:

```
province  = 'portugal'
community = 'portugal'
country   = 'ES'
```

`resolve_place` kept both as typed — neither matches a Spanish province or
community, and its documented policy is to preserve what the contributor saw —
so the ficha now asserts that Portugal is simultaneously a Spanish province and
a Spanish autonomous community, while declaring the country as Spain. It
appears in no province view and no community view. It was caught by eye,
reading the back of the bottle; nothing in the app could have flagged it.

What it unlocks besides correctness: the international waters Spanish
supermarkets actually stock (Evian, Perrier, San Pellegrino…), a 🌍 tier, and
country chips on the home page.

### Two items, and only one of them fixes anything today

An earlier version of this note said the official registry would already know
FONTÉBIL and that internationalisation was "one parser filter away". The PDF
was downloaded and read to check. **Both halves of that need correcting**, so
the work splits in two:

**(a) The model and the UI accept a non-`ES` water.** ✅ **Shipped** — `country`
is written on save from a closed vocabulary, the form offers it, `resolve_place`
no longer invents a Spanish province out of a Portuguese locality, and the
sitemap and the 🗺️ badge skip foreign waters. What remains of (a) is repairing
`fontebil`'s stored document, which is a Firestore write and the owner's call.

**(b) Parse the other 27 country tables.** This fixes *future* waters that the
registry does know. It does **not** fix FONTÉBIL, and it is the larger half —
see the measurements below. Its own item, not a prerequisite for (a).

### What the PDF actually says, measured

`refresh_aesan_snapshot.py` reads the EU-wide list
(`mineral-waters_list_eu-recognised.pdf`, 110 pages). Downloaded and parsed
directly:

- **28 country tables** — Austria through the United Kingdom. `_SPAIN` keeps
  Spain's, `_THIRD` drops the third-country one, `_OTHER` drops the remaining
  26. So (b) genuinely needs no new data source, only a parser that stops
  filtering. That much was right.
- **FONTÉBIL is not in it.** Neither is its bottler (Outeirinho), nor Fafe.
  Portugal's table has 29 real entries — Luso, Vidago, Monchique, Frize — and
  ours is not among them. Either it is *água de nascente*, a category this list
  does not cover, or it is registered under a name we do not have. **The
  registry cannot repair this ficha; a human has to.**
- **The place column has a different shape.** Portugal reads
  `Locality-Municipality` (`Vidago – Chaves`, `Sampaio-Vila Flor`), not
  `Municipality (Province)`. `_PROVINCE` matches on the closing parenthesis, so
  it would return nothing for every row of 26 tables. That was a suspicion
  here before; it is now checked.
- **The snapshot is current.** `AESAN_VERSION` reads `EU/2026-07-16` and the
  live PDF's own "Last update" is `16.07.2026` — the same document. The monthly
  refresh failing on a 429 therefore cost nothing; there was no new list to
  miss. Worth knowing before treating a failed run as urgent.

### What (a) has to avoid breaking

- `geo.community_of` is a Spanish province → autonomous community table.
  `submission.resolve_place` derives `community` from `province` and keeps
  unrecognised text as typed, which is exactly how `province='portugal',
  community='portugal'` happened — the failure `resolve_place` was written to
  prevent, arriving by a new door.
- The recommender's "nearby" (`geo.adjacent_places`) and the 🗺️ Cartógrafo
  badge (6+ provinces) both assume Spanish geography.

The shape that avoids a rewrite: **`country` decides whether a community is
expected at all.** A non-`ES` water declares country + a free-text region and
is excluded from province/community views rather than silently absent from
them. No geocoding service, no address parsing — the owner's call, and the
right one.

## be_water — the origin the camera never saw

`Una Dehesa` (id `fuente-dehesa`) was saved with no spring, province or
community, while `verified = True` over seven label-confirmed minerals.

This note used to say the cause was `label_ocr._PROMPT` scoping the field to
*"el lugar del manantial **en España**"*, and that rewording it was the fix.
**That was wrong, and the prompt needs no change.** Measured by running the
real `extract_label` against two photographs of the same bottle:

| Photo | `spring` | `province` | `community` | minerals |
|---|---|---|---|---|
| The back panel, address legible | `Encinas` | `Badajoz` | `Extremadura` | — |
| **The stored `label_photo_url`** | `None` | `None` | `None` | `tds=48`, `sodium=5.3` ✓ |

Same prompt, same model. The origin was simply **not in the frame**: the
composition shot frames the `ANÁLISIS QUÍMICO` panel, and the conservation
paragraph that carries `Herrera del Duque (Badajoz)` runs down the left edge,
rotated and clipped. The reader did not fail to understand the label — it was
never shown it.

So this is not an OCR item at all. It is the **second, optional label photo**
below, and this is its trigger: a ficha that reached `verified = True` with its
whole origin missing, because one face of the bottle answers the composition
question and another answers the origin one.

Nothing else here would have caught it either. An AESAN `place → province`
index — considered earlier — needs a municipality to key on, and the stored
document has none, for the same reason.
