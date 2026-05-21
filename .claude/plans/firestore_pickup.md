# Firestore migration — pickup notes

Branch: **`feat/firestore-migration`** (pushed, no PR). Reading this means you
came back from another task; here is exactly where we left off.

## State (2026-05-19/20)

Migration is **functionally validated** but not deployable yet. Five commits
on the branch:

1. `chore: add google-cloud-firestore (and restore matplotlib in api)`
2. `feat: Firestore SDK + Palmares model + from/to_firestore helpers`
3. `feat: backfill script to seed Firestore from existing CSVs`
4. `feat: DATA_BACKEND flag enables Firestore reads in the web`
5. `docs: pickup notes for the in-progress Firestore migration`

### Firestore in GCP

- `firestore.googleapis.com` enabled on `biwenger-tools`.
- `(default)` database, Native mode, **`europe-southwest1`** (regional, free
  tier, co-located with Cloud Run). No service-account key needed — ADC.
- **Populated** with the real CSV data via `scripts/backfill_firestore.py`:
  ```
  comunicados/24-25:    1 doc           comunicados/25-26: 133 docs
  participacion/24-25:  7 docs          participacion/25-26: 6 docs
  clausulazos/25-26:    104 docs        tabla_justicia/25-26: 7 docs
  palmares:             3 seasons
  ```

### Code

- `core/sdk/firestore.py` — `get_client`, `get_document`, `set_document`,
  `list_documents`, `query`, `count`, `batch_write` (500-op chunking),
  `delete_collection`. ADC auth.
- `core/domain/models.py` — added `Palmares` dataclass and
  `from_firestore`/`to_firestore` on every model. `fecha` is stored as a
  native Firestore timestamp; `from_firestore` formats it back to the
  display string the templates expect (per-model `_FECHA_FMT`).
- `packages/biwenger_tools/web/repository.py` — Firestore read helpers,
  returning the same models the CSV path produces. Sorting preserved:
  messages and clausulazos newest-first, tabla by `total_hechos` desc.
- `packages/biwenger_tools/web/config.py` — `DATA_BACKEND` env var
  (default `"csv"`). Route bodies in `routes/season.py` and
  `routes/main.py` early-return to firestore companions when
  `DATA_BACKEND == "firestore"`. **CSV branch left byte-identical** so the
  19 existing web tests pass unchanged.
- `scripts/backfill_firestore.py` — idempotent (delete-then-write each
  collection), deterministic clausulazo doc ids (content hash), count
  verification per collection.

### Tests + lint

- `//core:core_tests` green (10 new Firestore-related cases in
  `test_domain_models.py`; `test_firestore_sdk.py` is module-skipped without
  `FIRESTORE_EMULATOR_HOST`).
- `//packages/biwenger_tools/web:web_tests` green (CSV default keeps them
  on the unchanged path).
- Full sweep + `bash scripts/lint.sh` clean.

### Manual validation done

- `python3 scripts/backfill_firestore.py --csv-dir ~/Downloads/Biwenger`
  → every `cleared/wrote/count/expected` line matched.
- `DATA_BACKEND=firestore FIRESTORE_PROJECT=biwenger-tools \
  SESSION_COOKIE_SECURE=false PORT=8088 \
  bazel run //packages/biwenger_tools/web:web_local`
  + curl of `/version`, `/24-25/`, `/25-26/`, `/25-26/salseo`,
  `/25-26/mercado`, `/25-26/participacion`, `/palmares` → all 200, no
  error banners, content correct (fechas in display format, hechos
  rendered, emojis preserved).

## Pending before merge

1. **Scraper dual-write** (task #10). Right now the scraper only writes to
   CSV/Drive. After backfill, new messages would only land in CSV; once
   `DATA_BACKEND=firestore` is flipped in prod, the Firestore copy goes
   stale. Make `packages/biwenger_tools/scraper_job/main.py` write to
   Firestore (alongside CSV for a transition, then CSV-only is deleted in
   the cleanup PR). Models already have `to_firestore`; replicate the
   collection layout in `_write_and_upload_csv`.

2. **Rebuild + push `python-base`** (task #9). `docker/Dockerfile.base`
   already updated with `google-cloud-firestore==2.27.0`,
   `google-cloud-core==2.6.0`, `grpcio==1.80.0`, `grpcio-status==1.62.3`,
   plus `fonttools 4.62→4.63` and `numpy 2.4.4→2.4.6` (pip-compile bumps
   when the lock was regenerated). Needed before `DATA_BACKEND=firestore`
   in Cloud Run — Bazel local tests don't use this image, but the deployed
   container does.
   ```bash
   docker buildx build --platform linux/amd64,linux/arm64 \
     -f docker/Dockerfile.base \
     -t europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker/python-base:latest \
     --push .
   # grab the manifest sha256 from the push output and update MODULE.bazel,
   # then: bazel mod tidy
   ```
   Size budget: python-base was 275 MB; +grpcio ≈ 40 MB → ~315 MB, still
   inside the 500 MB Artifact Registry free tier.

3. **Flip the flag in deploy** (web only, after #2 lands). In
   `packages/biwenger_tools/web/BUILD.bazel` `extra_env` add
   `"DATA_BACKEND": "firestore"`. Default in `web/config.py` stays `csv`
   so local runs and tests keep their current behaviour unless overridden.

4. **Cleanup PR (separate, after #1–3 are stable)**. Plan step 6:
   - Delete the CSV branches from `routes/main.py` and `routes/season.py`,
     plus `_load_messages` and the `repository`-vs-inline duplication.
   - Drop `biwenger-tools-sa-regional` secret (Drive SA no longer needed —
     Firestore uses ADC).
   - Empty the Drive folder.
   - Retire `core.sdk.gcp.{find_file_on_drive, upload_csv_to_drive,
     download_csv_as_dict, get_sheets_data}` only if no consumer remains
     (Sheets reads for `lloros_awards` still need it for now).
   - Re-trim the unused entries from `docker/Dockerfile.base`.

## Quick resume commands

```bash
cd /Users/jorge/Projects/lillorepo
git fetch && git checkout feat/firestore-migration && git pull --ff-only

# Re-verify Firestore is still good
gcloud auth application-default print-access-token >/dev/null  # ADC sanity
python3 scripts/backfill_firestore.py --dry-run                # parses ok?

# Full test sweep + lint (should pass)
bazel test //core:core_tests \
  //packages/biwenger_tools/web:web_tests \
  //packages/biwenger_tools/scraper_job:scraper_job_tests \
  //packages/biwenger_tools/api:api_tests \
  //packages/biwenger_tools/bot:bot_tests \
  //packages/chucknorris_bot/bot:bot_tests
bash scripts/lint.sh

# Re-validate web reads against Firestore
DATA_BACKEND=firestore FIRESTORE_PROJECT=biwenger-tools \
  SESSION_COOKIE_SECURE=false PORT=8088 \
  bazel run //packages/biwenger_tools/web:web_local
```

## Decisions taken (don't reopen)

- Database location: regional `europe-southwest1`. Free tier; co-located
  with Cloud Run.
- Default `DATA_BACKEND=csv` so master stays safe; flag flips in deploy
  config, not in code.
- `fecha` stored as native Firestore timestamp, rendered back to the
  display string `from_firestore` so templates and sorting keep working.
- Clausulazo doc ids are a content hash (deterministic, idempotent), not
  Firestore auto-ids — strictly stronger than the plan's `auto_id`.
- Sheets reads (`lloros_awards`) stay on Sheets in v1; not part of this
  migration.

## Delete this file when

The migration ships to prod (`DATA_BACKEND=firestore` in `web/BUILD.bazel`)
and the cleanup PR has landed. Until then, this file is the single source
of truth for what is half-done.
