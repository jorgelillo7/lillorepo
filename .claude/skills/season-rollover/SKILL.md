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

# Step 2b — Generate palmares rows for the ending season

Before changing any files, fetch end-of-season data from the Biwenger API and produce the
CSV rows the user needs to paste into `palmares.csv` in Google Drive
(filename is `config.PALMARES_FILENAME` — currently `palmares.csv`).

## Precondition check

Look for `BIWENGER_EMAIL`, `BIWENGER_PASSWORD`, and `LEAGUE_ID` in the environment or in
`packages/biwenger_tools/web/.env`. If any are missing, skip the auto-fetch entirely and
tell the user they will need to fill in the palmares rows manually.

## Auto-fetch

If credentials are available, run the fetch script:

```bash
cd <repo_root>
BIWENGER_EMAIL=<email> BIWENGER_PASSWORD=<password> LEAGUE_ID=<id> \
  python .claude/skills/season-rollover/scripts/fetch_palmares.py <current_season>
```

Or, if `.env` files are present, source them first:

```bash
set -a && source packages/biwenger_tools/web/.env && set +a
python .claude/skills/season-rollover/scripts/fetch_palmares.py <current_season>
```

The script outputs ready-to-paste CSV rows for:
- `campeon`, `subcampeon`, `tercero`, `farolillo`, `puntuacion` — from standings API
- `clausulazos_total` — count of all release-clause transfers this season
- Placeholder rows for `record_puntos`, `jornadas_ganadas`, `multa`, `sancion` (manual)

If the script fails (auth error, network issue), continue with the rollover anyway.
Warn the user and print a blank template they can fill in manually:

```
<season>,campeon,RELLENAR
<season>,subcampeon,RELLENAR
<season>,tercero,RELLENAR
<season>,puntuacion,RELLENAR
<season>,farolillo,RELLENAR
<season>,clausulazos_total,RELLENAR
<season>,record_puntos,"RELLENAR — Jugador — X puntos (JY)"
<season>,jornadas_ganadas,"RELLENAR — Jugador — N jornadas"
<season>,multa,RELLENAR_O_BORRAR
<season>,sancion,RELLENAR_O_BORRAR
```

## Output

Present the rows to the user in the response. They paste them manually at the end of
`palmares.csv` in Google Drive. Do not upload or modify Drive files automatically.

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

### Palmares rows (paste manually into Drive)
The CSV rows for the ending season were generated by `fetch_palmares.py` and are printed
above. Paste them at the end of `palmares.csv` in Google Drive before or after merging.

### After merging
CI will deploy both services automatically with `TEMPORADA_ACTUAL=<new>`.
```

# Step 7 — Report

Show the user:
- The PR URL
- A reminder to update `.env` files on any other local machine
- Reminder that merging to `master` triggers the full CI deploy
