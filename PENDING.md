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

- **Live in production** (2026-07-18): 40 waters (top-11 OCU included),
  photo/OCR adds, admin-gated studio (credits bought, ~9.8€ left),
  water profile, /comunidad ranking + achievements, per-value
  provenance, /acerca. Regularization done 2026-07-19 (cost script
  covers both projects, cleanup covers both registries, docs swept).
  Roadmap, in order:
  1. **AESAN diff in catalog sync** (nice-to-have) — the monthly job
     shipped 2026-07-19 (Cloud Run Job + Scheduler, Telegram notify);
     what remains of the idea is diffing against the AESAN registry to
     flag newly recognised springs/waters.
  2. **Data verification pass** (USER-assisted): bottle-in-hand check of
     the ~25 seeded compositions; photos of labels to me work great.
     Full-label fichas now auto-promote to verified on save.
  3. **Country field — PARKED** (owner call 2026-07-19; analysis kept):
     add `country` to `Water` defaulting to "España" (backward compatible,
     one-line migration in `catalog_sync`). Unlocks international waters
     people actually find in Spanish supermarkets (Evian, Perrier,
     San Pellegrino…), a 🌍 achievement tier and country chips on the
     home. Revisit after the verification pass (item 2) — recommender
     places and province achievements assume Spanish geography and need
     a small rethink first.
  5. **Before going public** (LinkedIn/Twitter): Google Sign-In, CSRF on
     POST forms (generalise `biwenger_tools/web/csrf.py` into `core/`),
     abuse basics (rate limiting, input caps), and optionally a domain
     (~10 €/año, bought outside GCP).
  5b. **Admin page — gated on Google Sign-In** (owner decision 2026-07-18):
     users table (last_seen/created_at already tracked), contributions,
     block/ban and promote-to-admin. Deliberately NOT built on
     nickname-auth: banning a passwordless nickname is theatre. The
     public /comunidad ranking + achievements shipped separately.
