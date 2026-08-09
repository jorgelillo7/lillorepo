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
  - *Reusable deploy workflow* — **trigger is close to firing** (2026-08-07):
    six near-identical ~90-line deploy blocks, and the duplication has
    already cost something real — `chucknorris_bot` was missing from the
    cleanup script's `SIMPLE_IMAGES` and quietly accumulated 8 digests until
    2026-05-16. Still the riskiest refactor in the repo (YAML, untested,
    failures surface in prod), so it waits for a seventh service rather than
    for aesthetics.
  - *Ruff migration* — lint already runs hermetically via Bazel
    (black + flake8 from the lock, zero version drift, `scripts/lint.sh`).
    Trigger: flake8 blocks something real; speed is a non-issue here.
  - *Coverage in CI* — Bazel + pytest-cov plumbing (lock + every test
    target) outweighs the visibility gain. Trigger: a shipped regression that
    coverage would have caught — and the 2026-08-08/09 defects were **not**
    that. `/comparar` had the code written and unwired; the dead `suspended`
    branch *was* executed by tests, with a value JP never sends. Coverage sees
    neither.
  - *Gradual mypy* — start the day a type bug actually bites.
  - *Parametrised `base_deps` / Dockerfile.base from the lock* —
    build-system surgery, and **further away since #293**: the sync guard now
    catches the drift this would have prevented, at a fraction of the risk.
    Trigger: a package whose deps materially diverge from the base.
  - *Distroless base image* (evaluated 2026-08-07; see
    `docs/technical/backend/container-strategy.md`). Measured:
    `python:3.13-slim` 41,0 MB vs
    `distroless/python3-debian13` 21,4 MB — ~20 MB on a 159/512 MB free tier,
    while the bulk (matplotlib, numpy, grpcio, google-cloud) is identical
    either way. Costs a multi-stage rewrite of `Dockerfile.base` (distroless
    has no pip), the death of every `entrypoint.sh` (no shell), and
    revalidating the native wheels. The security win barely applies: Cloud Run
    has no `exec`, so there is no shell to reach. Trigger: cold start starts
    eating the 09:00 SLO, or the free tier gets tight.

- **OpenSpec authoring skill** (proposed 2026-07-27). A `.claude/skills/` skill
  to replace the OpenSpec npm CLI (deliberately not installed — no-installer
  preference). The third part, spec-lint, shipped as `scripts/check_specs.py`;
  these two remain:
  1. *Backfill mode* — point at a module → generate its
     `openspec/specs/<pkg>/<cap>/spec.md` from source + tests (Requirement /
     WHEN-THEN Scenario, scenario↔test links, GAP markers). Derives from code,
     asks nothing. This is how the current 21 specs were written by hand.
  2. *Propose mode* (spec-first / SDD) — describe a new feature →
     AskUserQuestion interview → draft `openspec/changes/<feature>/`
     (proposal + spec deltas) → approve → archive into `specs/`. Must delegate
     the *how* (implementation plan) to the existing `rpi-plan` skill — spec is
     the *what*, don't duplicate rpi.

## biwenger_tools

- **`nextMatch.status == "break"` — now waiting on itself** (2026-08-09). The
  optimizer reads it as "no fixture this week" and scores the player 0, and the
  value has never been observed: all 533 players report `pending`.
  `provider_watch` logs the first sighting, so this no longer needs anyone to
  remember to check — read the log after the first international break. If it
  never fires, delete the branch, as happened with `suspended`.

- **Decide what to do when the two providers disagree** (2026-08-09). No longer
  "nothing reads Biwenger's status" — rows carry it and `provider_watch` logs
  every disagreement. Two in 533 the day it shipped: JP `ok` vs Biwenger
  `injured` with an indefinite return, and JP `other` vs Biwenger `discarded`
  ("Sanción FIFA"). Still far too thin to override one provider with the other.
  Revisit once the log has a season's worth, which is the point of collecting
  them.

- **Nothing records whether a promoted substitute actually played**
  (2026-08-09, raised by the review of #311). `LINEUP_SUB_STARTS_ABOVE` decides
  every morning whether JP's predicted XI outranks its own projection, and the
  350 default is a judgement nobody can improve without knowing how often JP is
  right. The mechanism that makes the question urgent shipped; the log line
  that could answer it did not. `provider_watch` is the natural home.

- **A promotion can leave a line without bench cover** (2026-08-09, same
  review). Nothing bounds how many uncalled players clear the threshold at
  once. Three uncalled midfielders above it and three certain ones below, and
  all three start with an empty midfield bench slot — Biwenger's auto-sub
  replaces at most one per position. Not seen in a real squad yet; the shape
  is reachable, and a cap would be a policy decision rather than a fix.

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

  **BLOCKED ON A DECISION, not on the fix.** The league has not settled how the
  awards get updated during the season — Sheets or something else. Option (b)
  builds a Sheets-only service account, which is wasted work if Sheets is
  dropped. Waiting on that answer before spending the fix.

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
  1. **Data verification pass** — tooling shipped; two USER-OWNED manual
     runs remain (both prompt before every write, local via ADC):
     - `bazel run //packages/be_water/scripts:audit_photos -- --fix` — the 2
       fichas whose main photo never got the studio treatment.
     - `bazel run //packages/be_water/scripts:audit_data` — sign off the 5
       fichas eligible for verification.
     Ongoing: bottle-in-hand check of the remaining seeded compositions.
     Refresh the AESAN snapshot every few months with
     `packages/be_water/scripts/refresh_aesan_snapshot.py` — a git diff there
     means AESAN recognised new waters.

  2. **Country field — PARKED** (owner call 2026-07-19; analysis kept):
     add `country` to `Water` defaulting to "España" (backward compatible,
     one-line migration in `catalog_sync`). Unlocks international waters
     people actually find in Spanish supermarkets (Evian, Perrier,
     San Pellegrino…), a 🌍 achievement tier and country chips on the
     home. Revisit after the verification pass (item 1) — recommender
     places and province achievements assume Spanish geography and need
     a small rethink first.
  3. **Activate Google Sign-In + /admin** — all code shipped and dormant
     until the OAuth client exists. Only remaining step: the runbook in
     `packages/be_water/OPERATIONS.md` ("Activar Google Sign-In") — Console
     clicks plus one gcloud command, ~10 min. Custom domain PARKED.
