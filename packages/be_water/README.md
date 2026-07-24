# 💧 be_water

> **Status**: **in production** since 2026-07-18 (`be-water`, GCP project
> `be-water-app`). For operational detail, see:
>
> - **What shipped**: `release-notes.md` (next to this file).
> - **Commands and runbooks** (run, tests, deploy, catalog sync, curation /
>   audit tooling): `OPERATIONS.md` (in this package).
> - **Firestore data model**: `docs/firestore.md` (root) → `be-water-app` section.
> - **Pending follow-ups**: `PENDING.md` (root) → `be_water` section.
> - **Web design system**: `web/DESIGN.md`.

A collaborative catalog of Spanish bottled mineral waters, served with Flask on
Cloud Run. Anyone with the link photographs a bottle label and the entry fills
itself in (OCR via Gemini); the catalog crosses **mineral profile × origin** to
recommend waters similar to your favorites wherever you are.

## Main pieces (under `web/`)

- **App** (`app.py`) — catalog, water page, favorites, /comunidad (ranking +
  achievements), recommender, photo + OCR add flow, /acerca, /admin (dormant).
- **Data** — `domain.py` (`Water`, with **per-field provenance** in `sources`
  and `verified_fields`), `repository.py` (Firestore), `seed_data.py`,
  `aesan_snapshot.py` (official AESAN registry), `catalog_sync.py` (monthly sync).
- **Photos + AI** — `photos.py` (GCS + admin-gated *studio* treatment with
  Gemini), `label_ocr.py` (label OCR). Shared SDK in `core/sdk/gemini.py`.
- **Reusable engines** (also reused by `/admin`): `provenance.py` (derives each
  value's source), `photo_audit.py` (photo diagnosis/repair), `data_audit.py`
  (verification sign-off, duplicates, suspicious values), `similarity.py`.

## Data trust model

Every value carries its source (`label` / `manufacturer` / `manual` / `aesan`),
shown on the water page. An entry is **verified and locked** against overwrite
two ways: auto-promotion (every value label-backed) or admin sign-off (a
photographed label + at least one confirmed value). The official AESAN registry
supplies identity (name + spring + province); compositions always come from the
label, the legal source.

## Design decisions (the *why*)

- **Monorepo package + its own GCP project.** The code lives in lillorepo as a
  self-contained package (shares Bazel, `core/`, the `python-base` image, CI and
  PR discipline). The *runtime* runs in a separate GCP project (`be-water-app`):
  a Firestore free tier independent of the league's, attributable cost (its own
  €1 budget), and full isolation — nothing be_water does can touch the biwenger
  digest SLO. Same `deploy.yml`, different target via paths-filter + `--project`.
- **Similarity: normalized Euclidean distance in log-scale, in-memory k-NN.**
  The mineral vector is fixed (~10 dimensions), so the whole catalog fits in RAM
  and compares without vector infrastructure. Log-scale corrects the orders of
  magnitude (sodium ranges 0 to >1000 mg/L, TDS 20 to >4000): a 100 mg
  difference in TDS doesn't weigh the same as 100 mg in sodium. The
  location-based recommender reuses the engine: centroid of your favorites ×
  candidates from the area.
- **OCR via Gemini multimodal, not Cloud Vision.** One call with the photo + a
  structured schema returns the mineral vector already parsed as JSON, with no
  fragile per-label regex. A human reviews and corrects before saving; if Gemini
  fails, the form opens empty without losing the photo.
- **Lightweight "auth".** Nickname login (no password), enough for use among
  friends. Google Sign-In + /admin shipped dormant, ready to harden it when the
  group grows (runbook in `OPERATIONS.md`).

## Data sources

- [Official AESAN list](https://www.aesan.gob.es/AECOSAN/web/seguridad_alimentaria/subdetalle/lista_aguas_envasadas.htm)
  ([PDF](https://www.aesan.gob.es/AECOSAN/docs/documentos/seguridad_alimentaria/gestion_riesgos/lista_espanola.pdf))
  — official identity (name + spring + location); basis of the in-repo snapshot.
- [IGME — recognised mineral waters](https://aguasmineralesytermales.igme.es/introduccion/aguas-minerales-reconocidas)
  — geological inventory with a map viewer.
- **Real labels** (photos + Gemini) — the composition, always from the bottle.
- [mineralwaters.org](https://mineralwaters.org/) — cross-check for dubious compositions.
