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
    target) outweighs the visibility gain at 7 suites / 0.65 ratio.
    Trigger: a shipped regression that coverage would have caught.
  - *Gradual mypy* — start the day a type bug actually bites.
  - *Parametrised `base_deps` / Dockerfile.base from the lock* —
    build-system surgery guarded today by the add-python-dep skill.
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
  preference), in three parts:
  1. *Backfill mode* — point at a module → generate its
     `openspec/specs/<pkg>/<cap>/spec.md` from source + tests (Requirement /
     WHEN-THEN Scenario, scenario↔test links, GAP markers). Derives from code,
     asks nothing. This is how the current 21 specs were written by hand.
  2. *Propose mode* (spec-first / SDD) — describe a new feature →
     AskUserQuestion interview → draft `openspec/changes/<feature>/`
     (proposal + spec deltas) → approve → archive into `specs/`. Must delegate
     the *how* (implementation plan) to the existing `rpi-plan` skill — spec is
     the *what*, don't duplicate rpi.
  3. *(optional) spec-lint* — a `docs-audit`-style check: every `test_*` a
     scenario references still exists, every capability has a spec, closed GAPs
     are marked. This is what institutionalises openspec — an audit that warns,
     not a CI gate. (Mutmut stays on-demand by the same reasoning.)

## biwenger_tools

- **Compute the league's real points instead of calibrating to them**
  (2026-08-09). The league's exact scoring lives in its own settings as
  `settings.customScore` — a readable expression over minutes played, goals,
  assists, clean sheets, cards and MVP, with the >65-minute gate the draft
  analysis already reverse-engineered by hand. Today the rankings multiply a
  Jornada Perfecta projection by per-line factors measured once (0.225-0.610)
  because the two scoring systems differ; with the formula in hand that
  approximation is replaceable by a computation. Biggest remaining accuracy
  win, and it removes a constant that silently ages.

- **`nextMatch.status == "break"` is still a guess** (2026-08-09). The
  optimizer reads it as "no fixture this week" and scores the player 0. All
  533 players currently report `pending`; `break` has never been observed.
  Confirm during an international break, when the value should appear — or
  find it never does and delete the branch, as happened with `suspended`.

- **Consider reading Biwenger's own player status** (2026-08-09). Nothing
  reads it; JP is the only source. Biwenger currently marks 24 injured, 11
  doubt and 2 sanctioned, with human-readable notes and expected return dates.
  Worth it as corroboration when the two disagree, not as a replacement.

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
