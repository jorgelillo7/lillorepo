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
  restart) — delete the Drive folder contents (the old CSVs the scraper used to
  upload); then repoint `biwenger-tools-sa-regional` to a Sheets-only SA — do
  NOT drop it, the web still authenticates Sheets through that mount for
  `ligas_especiales` / `trofeos`.
- **Deferred audit items** (audit 2026-07-11, revisit when bored): reusable
  deploy workflow, gradual mypy, parametrised `base_deps` in `python_service`,
  Dockerfile.base generated from the lock, move `scripts/biwenger_*.py` into the
  package, `docs/README.md` index, dependabot for actions, typed SDK exceptions,
  ruff migration, coverage in CI.

## biwenger_tools

- **Season 26-27 award sheets** (USER-OWNED first step) — the Lloros Awards pages
  only have 25-26 sheets. When the user creates the 26-27 Ligas Especiales /
  Trofeos spreadsheets and shares the IDs: add the `*_26_27` GitHub secrets,
  wire them in `deploy.yml`, and extend the season→sheet maps in
  `web/config.py`. No rush — nothing to show until the league has data.

## my_photos

- **Photo-recognition project** — plan in `packages/my_photos/README.md`, not here.
  Blocked on USER: run the migration script and free up the disks.

## be_water

- **Sprint 1 shipped locally** (2026-07-17): catalog + favorites + similarity
  + geo-recommender running against the `be-water-app` project (created, with
  Firestore in europe-southwest1, billing and a €1 budget alert). Roadmap:
  1. **USER: validate the local UI** (`bazel run //packages/be_water/web:web_local`
     → localhost:8080) and merge PR #158.
  2. **Deploy to Cloud Run**: `be-water-docker` Artifact Registry repo in
     `be-water-app` (or cross-project pull), deploy-SA permissions, entry in
     `deploy.yml` with `--project be-water-app` + its paths-filter, smoke test.
  3. **Data verification pass** (USER-assisted): check the 15 seeded
     compositions bottle-in-hand, flip `verified: true` as they pass.
  4. **Sprint 1.B**: photo upload (GCS bucket `be-water-photos`) + Gemini OCR
     pre-fill (`core/sdk/gemini.py`, secret `GEMINI_API_KEY` — key comes from
     the user's AI Studio).
  5. **Before going public** (LinkedIn/Twitter): CSRF on the POST forms
     (generalise `biwenger_tools/web/csrf.py` into `core/`), and a pass on
     abuse basics (rate limiting, input caps).
