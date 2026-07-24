# Pending work

Long-running follow-ups that don't yet warrant a plan or PR.

**Rules of the file:**
- Never deleted; lives at the repo root.
- Lines are pruned as items ship or stop being relevant — keep it short.
- Group items by package; use `infra` for cross-cutting GCP/CI/policy tasks.
- "What has shipped" lives in `packages/biwenger_tools/release-notes.md` — do not duplicate here.

---

## infra

- **Drive folder cleanup** (USER-OWNED, actionable since the 2026-07-14 league
  restart) — the old scraper CSVs are DELETED (done 2026-07-24); the shared Drive
  now holds only the `ligas_especiales` / `trofeos` Sheets. Remaining step:
  repoint `biwenger-tools-sa-regional` to a Sheets-only SA — do NOT drop it, the
  web still authenticates Sheets through that mount for those sheets.
- **Parked by choice** (2026-07-19 review of the 2026-07-11 audit backlog;
  shipped from it: dependabot, docs index, scripts move, typed
  `BiwengerError`. Each survivor below waits for a trigger, not boredom):
  - *Reusable deploy workflow* — deploy.yml is stable; refactoring it
    risks prod for DRY aesthetics. Trigger: the next new service makes
    the duplication actively painful.
  - *Ruff migration* — lint already runs hermetically via Bazel
    (black + flake8 from the lock, zero version drift, `scripts/lint.sh`).
    Trigger: flake8 blocks something real; speed is a non-issue here.
  - *Coverage in CI* — Bazel + pytest-cov plumbing (lock + every test
    target) outweighs the visibility gain at 7 suites / 0.65 ratio.
    Trigger: a shipped regression that coverage would have caught.
  - *Gradual mypy* — start the day a type bug actually bites.
  - *Parametrised `base_deps` / Dockerfile.base from the lock* —
    build-system surgery guarded today by the add-python-dep skill.
    Trigger: a package whose deps materially diverge from the base.

## biwenger_tools

- **Season 26-27 award sheets** (USER-OWNED first step) — the Lloros Awards pages
  only have 25-26 sheets. When the user creates the 26-27 Ligas Especiales /
  Trofeos spreadsheets and shares the IDs: add the `*_26_27` GitHub secrets,
  wire them in `deploy.yml`, and extend the season→sheet maps in
  `web/config.py`. No rush — nothing to show until the league has data.
- **Lloros Awards empty for 25-26 — ROOT CAUSE FOUND (2026-07-24)** — both
  Awards tabs render empty because the Sheets read throws
  `google.auth.exceptions.RefreshError: invalid_grant: Invalid JWT Signature`
  BEFORE it ever touches the sheet (confirmed in `biwenger-summary` logs; the
  25-26 sheet IDs are correctly set as env vars and the sheets exist). The web
  service (`biwenger-summary` in europe-southwest1) authenticates Sheets with SA
  `biwenger-tools-sa@biwenger-tools.iam.gserviceaccount.com`, key
  `78fe38d4a8101834a9b138f8e26ee966e1eef3f5`, mounted via secret
  `biwenger-tools-sa-regional:latest`. That key is `disabled=True` (its only
  user-managed key) — almost certainly disabled during the SA-repoint / Drive
  cleanup work above. FIX, pick one: (a) quick —
  `gcloud iam service-accounts keys enable 78fe38d4a8101834a9b138f8e26ee966e1eef3f5
  --iam-account=biwenger-tools-sa@biwenger-tools.iam.gserviceaccount.com` then
  redeploy/restart the revision to clear cached creds; (b) clean (folds into the
  SA-repoint item) — create the Sheets-only SA, share the sheets with it, new
  key → new secret version → redeploy, leaving this key dead on purpose.
  (26-27 sheets simply not created yet — separate item above.)

- **Special-tournament winner images on Palmarés** (design agreed 2026-07-24;
  paused to finish be_water first) — new "Copas especiales" block per season on
  the `/palmares` page, rendered only when an image exists for that season.
  Storage: public GCS bucket `gs://biwenger-special-tournaments`
  (us-central1 / Standard / free-tier / UBLA + `allUsers:objectViewer` — ALREADY
  CREATED). Zero-backend by design: constructible URL
  `https://storage.googleapis.com/biwenger-special-tournaments/<slug>/<temporada>.png`
  with `<temporada>` = Firestore short id (`25-26`); template emits an `<img>`
  per known tournament with `onerror` to drop 404s, so new images need NO
  redeploy. To implement: `config.py` gets `SPECIAL_TOURNAMENTS_BUCKET` + a
  static registry `slug → label` (`santa-cup → "Copa Santa Claus"`,
  `castolo-cup → "Copa Castolo"`, more to come); the `palmares` route passes the
  base URL + list to the template; `palmares.html` gets the block inside the
  season loop (wrapper hidden if no image loads). A brand-new cup *type* = 1
  line in the registry (redeploy); new images for a known cup = none.
  Teammate write access GRANTED (`d.lucena9@gmail.com` -> `storage.objectCreator`).
  When the feature ships, document this bucket in the infra READMEs
  (`packages/biwenger_tools/web/README.md` + any infra/ops doc listing GCP
  resources) — it is currently undocumented.

## my_photos

- **Photo-recognition project** — plan in `packages/my_photos/README.md`, not here.
  Blocked on USER: run the migration script and free up the disks.

## be_water

- **Live in production** (2026-07-18): 40 waters (top-11 OCU included),
  photo/OCR adds, admin-gated studio (credits bought, ~9.8€ left),
  water profile, /comunidad ranking + achievements, per-value
  provenance, /acerca. Regularization done 2026-07-19 (cost script
  covers both projects, cleanup covers both registries, docs swept).
  Roadmap, in order:
  1. **Data verification pass** — curation tooling SHIPPED 2026-07-24
     (per-field provenance model + backfill, provenance badges on the ficha,
     admin sign-off, and the `audit_photos` / `audit_data` CLIs). Two
     USER-OWNED manual runs remain (both prompt before every write, local via
     ADC):
     - `bazel run //packages/be_water/scripts:audit_photos -- --fix` — the 2
       fichas whose main photo never got the studio treatment.
     - `bazel run //packages/be_water/scripts:audit_data` — sign off the 5
       fichas eligible for verification (label photo + label-confirmed values;
       the label-subset case auto-promotion can't reach).
     Ongoing (no tooling gap): bottle-in-hand check of the remaining seeded
     compositions — label photos to me work great; full-label fichas still
     auto-promote on save. The AESAN snapshot shipped 2026-07-19
     (`aesan_snapshot.py`, regenerate with
     `packages/be_water/scripts/refresh_aesan_snapshot.py` every few months — a
     git diff there = newly recognised waters; the official PDF is AMN/08 from
     2018, so refreshes are about catching AESAN's next revision).
  2. **Country field — PARKED** (owner call 2026-07-19; analysis kept):
     add `country` to `Water` defaulting to "España" (backward compatible,
     one-line migration in `catalog_sync`). Unlocks international waters
     people actually find in Spanish supermarkets (Evian, Perrier,
     San Pellegrino…), a 🌍 achievement tier and country chips on the
     home. Revisit after the verification pass (item 1) — recommender
     places and province achievements assume Spanish geography and need
     a small rethink first.
  3. **Activate Google Sign-In + /admin** — ALL CODE SHIPPED 2026-07-19
     (GIS button, credential verification via google-auth, /admin with
     users table + contributions + block/ban, blocked-user enforcement,
     admin emails via BEWATER_ADMIN_EMAILS). Dormant until the OAuth
     client exists; the ONLY remaining step is the runbook in
     docs/operations.md ("Activar Google Sign-In") — Console clicks +
     one gcloud command, doable by any model or human in ~10 min.
     Domain: PARKED (owner call 2026-07-19, alongside country).
     When it lands, the curation/photo engines (`data_audit`, `photo_audit`)
     are ready to surface in-page — same functions the CLIs already call.
