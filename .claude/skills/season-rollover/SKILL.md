---
name: season-rollover
description: Prepares all code changes needed to roll over to a new Biwenger season and opens a PR for review.
model-invocable: false
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - AskUserQuestion
---

# Goal

Prepare all changes required to start a new Biwenger season and open a pull request for review. The season change is a deliberate, manual decision — this skill automates the mechanical file edits, not the decision itself.

# Step 1 — Ask for the new season

Use `AskUserQuestion` to ask:
- What is the new season? (e.g. `26-27`)

Validate the format matches `^\d{2}-\d{2}$`. If it doesn't, explain the expected format and ask again.

# Step 2 — Read current state

Read these files to understand the current season and build the exact diffs needed:

- `.github/workflows/deploy.yml` — find `TEMPORADA_ACTUAL` in the `env:` block
- `packages/biwenger_tools/web/config.py` — find `TEMPORADA_ACTUAL` and `TEMPORADAS_DISPONIBLES`
- `packages/biwenger_tools/scraper_job/config.py` — find `TEMPORADA_ACTUAL`
- `packages/biwenger_tools/web/.env` — find `TEMPORADA_ACTUAL`
- `packages/biwenger_tools/scraper_job/.env` — find `TEMPORADA_ACTUAL`
- `docs/operations.md` — find the manual `--update-env-vars TEMPORADA_ACTUAL=` reference

Note: `api`, `bot`, and `chucknorris_bot` do **not** use `TEMPORADA_ACTUAL`
(verified 2026-05-12 — they don't have season-specific data paths). Do not add them to the edit
list unless a future grep finds new references.

Extract the current season value from `deploy.yml`. If the new season matches the current one, warn the user and stop.

# Step 2b — Generate the palmares Firestore doc for the ending season

Before changing any files, fetch end-of-season data from the Biwenger API and write
the Firestore document at `palmares/<season>` with the full per-user standings table.
Firestore is the only destination — the web reads from there directly.

## Precondition check

Look for `BIWENGER_EMAIL` and `BIWENGER_PASSWORD` in the environment or in
`packages/biwenger_tools/scraper_job/.env` (the api module's .env works too —
they share the same Biwenger credentials). `LEAGUE_ID` defaults to
`core.constants.LEAGUE_ID` if not set in the environment. If the Biwenger
credentials are missing, skip the auto-fetch entirely and tell the user
they will need to write the palmares doc manually in the Firestore console.

For `--write-firestore` the script needs ADC: a local `gcloud auth
application-default login` against the project that hosts the palmares
Firestore (the same one the web reads from).

## Ask about abandoned accounts

Before running the fetch, ask the user if anyone deleted their Biwenger account during
the season — those accounts disappear from the standings/report APIs, so they need to be
injected manually. Collect a list of `NAME=TEAM=REASON` triples — the team is the
Biwenger team name the abandoned account had (so the palmarés card still shows it);
leave the team slot empty if unknown.

## Auto-fetch

If credentials are available, source the env file and run the fetch script. Pass each
abandoned account with one `--abandoned-user` flag. First run without
`--write-firestore` so the user can review the JSON preview, then re-run with the
flag to push:

```bash
set -a && source packages/biwenger_tools/scraper_job/.env && set +a

# Preview (no Firestore write)
python .claude/skills/season-rollover/scripts/fetch_palmares.py <current_season> \
  --abandoned-user "Alberto=#NOALOSCLAUSULAZOS=abandono"

# Push to Firestore once the preview looks right
python .claude/skills/season-rollover/scripts/fetch_palmares.py <current_season> \
  --abandoned-user "Alberto=#NOALOSCLAUSULAZOS=abandono" \
  --write-firestore
```

The script combines three Biwenger endpoints (standings, report/rounds,
report/roundPoints) and outputs two blocks:

1. **Firestore doc preview** — the full document at `palmares/<season>` with the
   per-user standings table (points, best/worst round, rounds won, average position).
2. **Per-user table** — terminal-friendly summary.

If the script fails (auth error, network issue), continue with the rollover anyway
and tell the user to write the doc manually in the Firestore console under
`palmares/<season>`. The required field shape is documented in `core.domain.models`
(`Palmares.to_firestore()` / `SeasonStanding.to_firestore()`).

If `palmares/<season>` already exists, `--write-firestore` refuses to overwrite
and exits non-zero with a clear message. Add `--force` if a deliberate rewrite
is needed (e.g. you corrected an `--abandoned-user` typo and want to push the
fix). Default behaviour is "write once, never clobber".

## Output

Show the user the Firestore doc preview and the per-user table. If `--write-firestore`
landed, mention the doc has been written; otherwise tell them to either re-run with
the flag or paste the JSON in the Firestore console manually.

# Step 3 — Create a branch

```bash
git checkout -b season-rollover-<new_season>
```

Where `<new_season>` uses hyphens (e.g. `season-rollover-26-27`).

# Step 4 — Apply the changes

Make all edits. For each file, use Edit (never Write) since these are existing files:

**`.github/workflows/deploy.yml`**
- Replace `TEMPORADA_ACTUAL: "<current>"` with `TEMPORADA_ACTUAL: "<new>"`

**`packages/biwenger_tools/web/config.py`**
- Replace `TEMPORADA_ACTUAL = os.getenv("TEMPORADA_ACTUAL", "<current>")` with the new default
- Append the new season to `TEMPORADAS_DISPONIBLES` (keep all existing ones)

**`packages/biwenger_tools/scraper_job/config.py`**
- Replace `TEMPORADA_ACTUAL = os.getenv("TEMPORADA_ACTUAL", "<current>")` with the new default

**`packages/biwenger_tools/web/.env`**
- Replace `TEMPORADA_ACTUAL="<current>"` with the new value

**`packages/biwenger_tools/scraper_job/.env`**
- Replace `TEMPORADA_ACTUAL="<current>"` with the new value

**`docs/operations.md`**
- Replace the `--update-env-vars TEMPORADA_ACTUAL=<current>` references with the new value (there may be more than one — replace all)

# Step 5 — Commit

Stage only the files changed above (never use `git add -A`):

```bash
git add \
  .github/workflows/deploy.yml \
  packages/biwenger_tools/web/config.py \
  packages/biwenger_tools/scraper_job/config.py \
  docs/operations.md
git commit -m "chore: roll over to season <new_season>"
```

Do NOT commit `.env` files — they are gitignored and contain secrets.

# Step 6 — Push and open PR

```bash
git push -u origin season-rollover-<new_season>
```

Then create the PR with `gh pr create`:

```
Title: "chore: season rollover <current> → <new>"

Body:
## Season rollover: <current> → <new>

Automated changes prepared by the `season-rollover` skill.

### Files changed
- `.github/workflows/deploy.yml` — `TEMPORADA_ACTUAL` updated
- `packages/biwenger_tools/web/config.py` — default updated, `<new>` added to `TEMPORADAS_DISPONIBLES`
- `packages/biwenger_tools/scraper_job/config.py` — default updated
- `docs/operations.md` — manual commands updated

### Not included (local only, gitignored)
- `web/.env` and `scraper_job/.env` — updated locally, not committed

### Palmares
The Firestore doc `palmares/<current>` was written by `fetch_palmares.py` (or printed
above for manual paste into the Firestore console if `--write-firestore` was skipped).

### After merging
CI will deploy both services automatically with `TEMPORADA_ACTUAL=<new>`.
```

# Step 7 — Report

Show the user:
- The PR URL
- A reminder to update `.env` files on any other local machine
- Reminder that merging to `master` triggers the full CI deploy
