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

**(a) The model and the UI accept a non-`ES` water.** This is what fixes the
broken ficha, and it is the small half: write `country` on save, offer it on
the form, keep `resolve_place` from inventing a Spanish province out of a
Portuguese locality, and skip non-`ES` waters in the province/community views
instead of letting them fall out silently.

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

## be_water — repairing a ficha from the admin page

`/admin` shows users and stranded photos. It cannot edit a water. Every repair
— a missing community, a province that is really a municipality, a wrong
source — runs through `scripts/audit_data.py` on a laptop with credentials, or
by re-submitting the public add form and letting the merge rules win.

Two waters added in one sitting made the gap concrete: one reached Firestore
with no province (Badajoz was on the label and was not read), the other is
Portuguese and has no province to have.

Most of the engine is already built and tested — this is wiring, not new
logic:

| Need | Already exists |
|---|---|
| Change a mineral + its provenance | `data_audit.correct_field` / `set_source` |
| Sign off a ficha | `data_audit.mark_verified` |
| Fold a duplicate | `data_audit.merge_waters` |
| Community-only write | `repository.set_water_community` |
| Undo trail before an overwrite | `repository.save_revision` + `scripts/revert_water.py` |
| Province / community vocabulary | `geo.ALL_PROVINCES`, `geo.ALL_COMMUNITIES` |

**Use selects, not free text.** `resolve_place`'s docstring records what free
text cost once: `tramuntana` reached Firestore with `province="Talarrubias"`
(a municipality) and `community="Badajoz"` (a province), shifted one slot, and
vanished from every province and community view. An admin form that offers the
two canonical lists cannot reproduce that.

**Blocked on:** Google Sign-In. `admin_page` 404s while `GOOGLE_CLIENT_ID` is
unset, so there is nowhere to put the form until that is configured.

## be_water — the province the OCR did not read

`Una Dehesa` (id `fuente-dehesa`) was saved with **no origin at all**:

```
spring = ''   province = ''   community = ''
```

— while `verified = True` over seven label-confirmed minerals. The OCR read the
composition panel perfectly and returned nothing for the origin.

The label prints it: `06670 Herrera del Duque (Badajoz), España`, inside the
small-print conservation paragraph, as the bottler's postal address.

Likely cause: `label_ocr._PROMPT` scopes the field to *"el lugar del manantial
en España"*, so a bottler address is not obviously an answer to the question
asked.

**The fix is the prompt, and only the prompt.** An AESAN `place → province`
index was considered — the snapshot does contain `Herrera del Duque → Badajoz`
— but it is dead for this case and would not have helped: there is no
municipality in the stored document to key it on, because the OCR returned no
place either. A backstop needs something to back up.

Two independent things to say in the prompt: that the bottler's address is an
acceptable fallback when no origin is printed elsewhere, and that `(Provincia)`
inside an address is the province.

## be_water — the curation engine cannot see a broken province

`data_audit` flags suspicious **minerals** (`suspicious_reasons`) and gates
verification on a label photo plus one confirmed field (`verifiable`). Nothing
in it looks at geography.

`fontebil` is `verified = True` with `province = 'portugal'`. Both of the two
broken fichas in the catalog would pass every check the curation engine has.

A geo check — province in `geo.ALL_PROVINCES`, community derivable from it,
or an explicit non-`ES` country — is small, self-contained, and would have
caught both. It also gives the admin edit page its worklist for free.

**Sizing, measured against the live catalog:** 2 fichas of 51 have a geo gap.
Small enough that this is not urgent, and the honest argument for doing the
Biwenger work first.

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
