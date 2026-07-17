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

- **Live in production** (2026-07-18): 25 waters (2 label-verified), public
  URL, deploy pipeline, idempotent catalog sync with Telegram notify.
  Roadmap, in order:
  1. **Sprint 1.B — photo upload + Gemini OCR**: GCS bucket
     `be-water-photos`, `core/sdk/gemini.py` (new dep `google-genai` via
     the add-python-dep skill), secret `GEMINI_API_KEY`. Reuse the user's
     existing AI Studio key (project `gen-lang-client-0434934257`, the one
     renamed "lillorepo" during the GCP cleanup) — no new project.
  2. **Regularization review** — validate that be_water is a properly
     separate GCP project riding the generic monorepo machinery:
     - `scripts/check-gcp-costs.sh`: audits `biwenger-tools` only; make it
       cover both projects (be-water-app: €1 budget, be-water-docker
       registry, Firestore, 2 secrets, Cloud Run minScale=0, no scheduler).
     - `scripts/clean-images-artifact.sh`: extend to `be-water-docker`
       before old `web` digests pile up.
     - Skills sweep: `add-python-dep` already lists be_water reqs ✓;
       `check-deps` is project-agnostic ✓; decide when be_water gets its
       own `release-notes.md` (the skill supports multiple packages).
     - Docs sweep: `docs/gcp.md` is biwenger-only → add be-water-app
       (secrets, cross-project deploy IAM, budget); `docs/operations.md`
       → be_water module section (targets, sync_local, deploy, URL);
       root README packages table → be_water no longer "in planning";
       workflows README → document the cross-project deploy grants.
     - Folder hygiene: anything generic worth hoisting to `core/`/`tools/`
       (candidate: csrf.py; `core/sdk/gemini.py` lands shared by design).
  3. **Monthly catalog sync as a scheduled job** — run `catalog_sync` as a
     Cloud Run Job + monthly Scheduler tick (Telegram creds via secret,
     already stored); ideally diff against the AESAN list to flag newly
     recognised waters.
  4. **Data verification pass** (USER-assisted): bottle-in-hand check of
     the ~25 seeded compositions; photos of labels to me work great.
  5. **Recommender: nearby-province fallback** — Madrid is the canonical
     case (no big bottled AMN brand): fall back to bordering provinces.
     Needs a province-adjacency map in the repo.
  6. **Before going public** (LinkedIn/Twitter): Google Sign-In, CSRF on
     POST forms (generalise `biwenger_tools/web/csrf.py` into `core/`),
     abuse basics (rate limiting, input caps), and optionally a domain
     (~10 €/año, bought outside GCP).
