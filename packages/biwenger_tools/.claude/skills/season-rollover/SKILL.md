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
- `packages/biwenger_tools/OPERATIONS.md` — find the manual `--update-env-vars TEMPORADA_ACTUAL=` reference (§ Cambio de temporada)

Note: the `api` service **does** consume `TEMPORADA_ACTUAL` — it backs
`config.DRAFT_SEASON`, which keys the `draft/{season}/...` Firestore layout.
It is passed in `deploy.yml`'s `deploy-api` step, so the single `env:` bump
covers it; no separate edit is needed, but do not assume the api is
season-agnostic. `bot` and `chucknorris_bot` still have no season-specific
data paths.

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

## Ask who won the cups

The Biwenger API knows nothing about the Copa Santa Claus or the Copa Castolo —
they are league inventions — so ask the user for each winner: the manager and
the Biwenger team name they held. Pass them as `--cup-winner SLUG=NAME=TEAM`,
where the slug is the one in `web.config.SPECIAL_TOURNAMENTS` (`santa-cup`,
`castolo-cup`).

Without this the palmarés still renders the winner graphics, but nobody can
tell who won without opening the image — which is exactly what the `copas`
field exists to avoid.

Remind the user to upload the two graphics as well; without them the block is
empty. Runbook: `packages/biwenger_tools/OPERATIONS.md` §1.

## Auto-fetch

If credentials are available, source the env file and run the fetch script. Pass each
abandoned account with one `--abandoned-user` flag. First run without
`--write-firestore` so the user can review the JSON preview, then re-run with the
flag to push:

```bash
set -a && source packages/biwenger_tools/scraper_job/.env && set +a

# Preview (no Firestore write)
python packages/biwenger_tools/.claude/skills/season-rollover/scripts/fetch_palmares.py <current_season> \
  --abandoned-user "Alberto=#NOALOSCLAUSULAZOS=abandono" \
  --cup-winner "santa-cup=Fabio=Rayo Entrebirras" \
  --cup-winner "castolo-cup=Jorge=Farolillo Oracle United"

# Push to Firestore once the preview looks right
python packages/biwenger_tools/.claude/skills/season-rollover/scripts/fetch_palmares.py <current_season> \
  --abandoned-user "Alberto=#NOALOSCLAUSULAZOS=abandono" \
  --cup-winner "santa-cup=Fabio=Rayo Entrebirras" \
  --cup-winner "castolo-cup=Jorge=Farolillo Oracle United" \
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

# Step 2c — Draft parameters for the new season

Three values change every season. They are code constants, so they drift
silently if skipped — a wrong order does not fail, it just makes people pick in
the wrong turn for fifteen rounds.

**Suggest the new order, do not ask cold.** The `palmares/<ending_season>` doc
written in Step 2b holds the final classification, and the draft order is its
reverse. Read it and propose that reversal:

```bash
python3 packages/biwenger_tools/.claude/skills/season-rollover/scripts/suggest_draft_order.py <ending_season>
```

The script inverts the final classification, drops non-playing accounts (which
the palmarés stores with `user_id=0`, so an id check alone misses them) and
places anyone with no previous classification in the middle, per the
reglamento's rule for newcomers.

Confirm with `AskUserQuestion` before applying — never unattended. The script
covers the ordinary case; the reglamento may still call for an adjustment it
cannot know about.

Then edit:

1. **Snake order** — `core/constants.py`, `DRAFT_ORDER_NAMES`. **One place
   only**: the api arbitrates the draft with it and the web publishes it on the
   rulebook page, both reading the same constant. Names must match
   `LEAGUE_MEMBERS` values (accent/case-insensitive).
2. **Budget overrides** — `packages/biwenger_tools/api/logic/draft.py`,
   `BUDGET_OVERRIDES`. The Copa Castolo winner carries a +2M draft bonus into
   the new season. Keyed **by manager id**, never by draft position — the order
   changes yearly, so a positional key would silently hand the bonus to
   whoever happens to pick third.
3. **League membership** — `core/constants.py`: `LEAGUE_MEMBERS` and
   `NON_PLAYING_MEMBER_IDS`, if anyone joined, left, or switched between
   playing and spectating.

**The rulebook page needs no edit for any of this.** `/reglamento` renders the
draft order from `DRAFT_ORDER_NAMES` and derives its season label from
`TEMPORADA_ACTUAL`. What it does *not* track is the rules themselves: if the
reglamento document changed, that is a separate content pass over
`packages/biwenger_tools/web/templates/reglamento.html`. Ask the user whether
this season's document changed, and say plainly that nothing automatic will
catch it if it did.

Also remind the user that the frozen market CSV is a manual per-season
artifact: exported on the agreed market-close day and uploaded to
`gs://biwenger/draft/<new_season>/market.csv` (see
`openspec/specs/biwenger_tools/draft/spec.md`). Nothing auto-downloads it —
a late export carries the wrong prices.

# Step 3 — Create a branch

```bash
git checkout -b season-rollover-<new_season>
```

Where `<new_season>` uses hyphens (e.g. `season-rollover-26-27`).

# Step 4 — Apply the changes

Make all edits. For each file, use Edit (never Write) since these are existing files:

**`.github/workflows/deploy.yml`**
- Replace `TEMPORADA_ACTUAL: "<current>"` with `TEMPORADA_ACTUAL: "<new>"`
- In the `Deploy web to Cloud Run` step, add
  `COMPETICIONES_SHEET_IDS_<NEW_UNDERSCORED>=${{ secrets.COMPETICIONES_SHEET_IDS_<NEW_UNDERSCORED> }},\`
  to `--set-env-vars`, next to the existing seasons'. Put nothing but flags
  between the backslash-continued lines: a comment there consumes the rest of
  the command and the deploy exits 126 having applied only half of it.

**`packages/biwenger_tools/web/config.py`**
- Replace `TEMPORADA_ACTUAL = os.getenv("TEMPORADA_ACTUAL", "<current>")` with the new default
- Append the new season to `TEMPORADAS_DISPONIBLES` (keep all existing ones)
- Add the new season to `COMPETICIONES_SHEETS`:
  `"<new>": _sheet_ids("COMPETICIONES_SHEET_IDS_<NEW_UNDERSCORED>")`
  (e.g. `27-28` → `COMPETICIONES_SHEET_IDS_27_28`). Leave the old seasons in
  place — they are the archive the season selector reaches.

**`packages/biwenger_tools/scraper_job/config.py`**
- Replace `TEMPORADA_ACTUAL = os.getenv("TEMPORADA_ACTUAL", "<current>")` with the new default

**`packages/biwenger_tools/web/.env`**
- Replace `TEMPORADA_ACTUAL="<current>"` with the new value

**`packages/biwenger_tools/scraper_job/.env`**
- Replace `TEMPORADA_ACTUAL="<current>"` with the new value

**`packages/biwenger_tools/OPERATIONS.md`**
- Replace the `--update-env-vars TEMPORADA_ACTUAL=<current>` references with the new value (there may be more than one — replace all)

# Step 4b — The competitions workbook for the new season

The competitions page (Liga H2H, copas, trofeos) reads whatever tabs live in
the spreadsheets the season points at. Without this step the new season rolls
over with an empty page and nobody notices until someone opens it — which is
how the awards pages stayed dark for a year.

Ask the user for the new season's workbook id (the string in its Sheets URL
between `/d/` and `/edit`), then:

1. Confirm the sheet is shared with the Sheets service account, or every read
   returns 403 and the page falls back to the bare H2H calendar:
   `biwenger-tools-sa@biwenger-tools.iam.gserviceaccount.com` (Viewer).
2. Create the GitHub secret:
   ```bash
   gh secret set COMPETICIONES_SHEET_IDS_<NEW_UNDERSCORED> --body "<id>"
   ```
   Several workbooks in one season are separated by **`;`**, never by a comma:
   `--set-env-vars` splits its own argument on commas and the deploy fails
   with `Bad syntax for dict arg`.

Nothing inside the workbook is configured. A tab whose header row starts
`Jornada | Partido` is the H2H fixture block; a tab whose A1 reads `Nombre de
la liga` is a table competition; anything else is reported on the page. The
league adds a competition by adding a tab.

# Step 5 — Commit

Stage only the files changed above (never use `git add -A`):

```bash
git add \
  .github/workflows/deploy.yml \
  packages/biwenger_tools/web/config.py \
  packages/biwenger_tools/scraper_job/config.py \
  packages/biwenger_tools/OPERATIONS.md
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
- `packages/biwenger_tools/OPERATIONS.md` — manual commands updated

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
- **Special-cup winner images**: once the `palmares/<ending_season>` doc exists
  (Step 2b), the `/palmares` "Copas especiales" block renders for that season.
  Remind the user they can upload the winner graphics — no redeploy needed —
  with the filename matching the palmarés doc id (e.g. `25-26`):
  ```bash
  gcloud storage cp copa-santa.jpg \
      gs://biwenger/special-tournaments/santa-cup/<ending_season>.jpg
  gcloud storage cp copa-castolo.jpg \
      gs://biwenger/special-tournaments/castolo-cup/<ending_season>.jpg
  ```
  (Slugs live in `config.SPECIAL_TOURNAMENTS`; see `packages/biwenger_tools/OPERATIONS.md` §1.)
