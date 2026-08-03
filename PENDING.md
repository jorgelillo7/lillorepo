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

### Skill de draft

Todo lo aprendido en el draft 26-27. La skill vive en
`.claude/skills/draft/`; estos son sus arreglos pendientes.

- **Draft skill — international tournaments and player nationality.** The
  frozen market CSV carries team, position, points and price but **no
  nationality**, so "who disappears mid-season for a national-team
  tournament" can only be answered by eyeballing names — unreliable, and it
  silently misses anyone whose name does not read as foreign. It bit this
  season: AFCON 2027 moved to summer (19 Jun – 17 Jul, no LaLiga impact),
  while the **AFC Asian Cup runs 7 Jan – 5 Feb 2027**, taking matchdays
  ~20-24. The two affected LaLiga players were found by grep (Kubo, Kang-in
  Lee) and happened to be irrelevant on score, but the method does not
  generalise. FIX: check whether JP's payload carries nationality (it may —
  `core/sdk/jp.fetch_all_players` returns the raw player dicts); if so, join
  it in `draft_ranking.py` and give `archetypes.py` a
  `--tournament-absences` flag taking the affected federations. Also make
  "which international tournaments fall inside this season, and who do they
  take" an explicit step of the skill rather than an assumption — the answer
  inverted between two consecutive editions.

- **Draft skill — the generator ignores that this is a draft.** It builds the
  ideal 15 as if every player were purchasable, but picks are taken in snake
  order: at position 3 of 7, nine players leave the board between the first
  and second pick. The per-tier target lists that make the output actionable
  are currently assembled by hand each year. A `--pick-position N` that
  printed realistic availability windows per pick would close the gap.

- **Draft skill — placeholder players are only filtered in the generator.**
  `draft_ranking.py` writes them into the ranked CSV with
  `no_jp_data=False`, so the intermediate file shows a flat `SF 400` that
  looks like real data (Amatucci, Noubi, Puga, Calero this season).
  `archetypes.py` drops them correctly, but anyone reading the CSV directly
  is misled. Flag them in the ranking output too.

- **Draft skill — it ranked by the wrong metric (found 2026-08-01, mid-draft).**
  The league scores **"Personalizado"**, and the skill ranked by JP's SofaScore
  projection. Not a small gap: the real/projection factor ranges **0.225
  (Terrats) to 0.610 (Dmitrović)** across 22 players measured this season, so a
  single conversion factor cannot compare individuals. Converting is a dead end;
  the fix is to **fetch the real number for the shortlist**. Concretely:
  - **Two phases.** Phase A stays as-is — JP ranks the whole ~500-player market
    and produces a shortlist. Phase B fetches real Personalizado points for the
    shortlist only. **Size it at 30-45, not 15**: the whole point of phase B is
    that it reorders, and this season Dmitrović (6th keeper by projection, 1st by
    real points) and Juan Iglesias (not in the squad at all → captain) would both
    have been outside a 15-name list.
  - **`draft-real-points.csv` with `name,points,games`.** Games are mandatory:
    Guido's "116" was meaningless until "from matchday 22" turned it into ~218.
    The optimiser prefers real over projection and marks which is which.
  - **Calibrate per line when projecting.** Median factor is **0.458 for
    keepers vs 0.371 for outfielders** — a 23% systematic gap, because clean
    sheets pay +2 here but barely move a SofaScore rating. One global factor
    buried the best keeper in the market.
  - **Provenance column in the final report** (`✅ real / ⚠️ partial /
    ~ projection / 🎲 bet`). Hand-written this year; it was the most-used column
    of the session.

- **Draft skill — fit the custom bonus table from this season's data.**
  `GET /players/la-liga/{slug}?fields=*,reports(*)` returns per-match `rawStats`
  (`win`, `cleanSheet`, `minutesPlayed`, base score), which is enough to
  reconstruct a Personalizado total — *if* the bonus table is known. It is not:
  `SofaScore + 2×wins + 2×clean sheets` and `Marca + 2×wins` both fit Joan
  García's 274 exactly. There are now **22 verified totals** from this draft;
  solve the table against those. If it closes, phase B becomes one request per
  candidate instead of asking the user to read numbers off the app. If it does
  not, record that and keep reading them by hand.

- **Draft skill — the timings backfill leaves a one-pick hole.**
  `scripts/backfill_draft_timings.py` writes `applied_at`/`waited_seconds` onto
  the pick documents but not `turn_started_at` onto the state document. The live
  code measures from that field, so the first pick after the backfill has
  nothing to measure against and lands blank — it happened on pick 49 of the
  26/27 draft and was patched by hand. FIX: have the backfill also stamp
  `turn_started_at` with the last matched pick's timestamp, so the handover to
  live tracking is seamless.

- **Draft skill — the fetcher must be bounded (learned the hard way).**
  Biwenger's quota is **500 requests per 8-hour window, per account** (read off
  the `429` headers: `x-rate-limit-limit: 500`). Pulling all ~550 players in
  parallel locked the whole league out of the app for 8 hours **mid-draft**,
  including the bot. The rule is written into `SKILL.md`; the tool that enforces
  it does not exist yet: shortlist only, sequential with a delay, checkpoint to
  disk, stop on the first 429 instead of retrying.

- **Draft skill — news due-diligence is entirely manual.** This season it
  produced three exclusions that changed the squad (Aubameyang: score earned
  in Ligue 1, now at a promoted side, 37; Carlos Soler: knee injury since
  December 2024, playing with the reserves; Kike Salas: under investigation
  for booking-related betting fraud). They live in a `--exclude` command-line
  flag, so nothing records *why* a player was banned. An `--exclude-file`
  with a per-season, commented list would version the reasoning.
  **Make it a blocking step, not an optional one.** It was skipped this season
  until the user asked for it mid-draft, and it immediately turned up three
  things the numbers could not see: Marcos Alonso left out of the pre-season
  squad pending a renewal, Canales returning at 35 from three years in Liga MX
  (so his only good figure was from 2022/23 at Betis), and Fortuño competing
  with Dmitrović for the Espanyol goal — on a keeper meant to be kept unclausable
  all season.

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
