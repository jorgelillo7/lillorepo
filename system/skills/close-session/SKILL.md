---
name: close-session
description: Close a working session across the owner's main repos — keep the reusable scripts the session wrote, bring every PENDING.md and parked-work note in line with what shipped, pull the vendored skills, offer release notes, and report the state of each step. Use when the owner says the session is done or asks to wrap up ("cierra la sesión", "cerramos", "close session").
model-invocable: false
---

# Close a session

A session leaves work in four places nobody looks at again: scripts written in
the scratchpad, follow-up docs that no longer match what shipped, vendored skills
that went stale, and release notes nobody wrote. This skill walks each one and
ends with a status line per step (the `lists` rule).

Every step that changes a repo goes through a branch and a PR, as `git.md` says;
a merge needs the owner's word unless they gave it for this session.

## The repos

| Repo | Follow-up docs | Notes |
|---|---|---|
| `~/Projects/lillorepo` | `PENDING.md`, `docs/technical/parked-work.md` | Also holds `system/` (skills, rules, agents) and the sync scripts |
| `~/Projects/household` | `PENDING.md` | |
| `~/Projects/lillo-android-apps` | `PENDING.md`, `docs/plans/` | |
| `~/Projects/jorgelillo7.github.io` | `PENDING.md` | |

Never enter `~/Projects/retrofit` (work). `~/Projects/project-silent-hill` is
another person's repository: pull only, change nothing.

## 1. What the session touched

For each repo: `git fetch --prune`, then the branch, uncommitted changes,
unpushed commits, open PRs by the owner (`gh pr list --author @me`) and PRs
merged since the session began (`gh pr list --state merged --search
"merged:>=<date>"`). This list is the input to every step below. A repo with
uncommitted work is reported, never committed for the owner.

## 2. Scripts the session wrote and did not keep

Look in the session's scratchpad (the system prompt names it) for scripts
(`*.py`, `*.sh`, `*.mjs`, `*.ts`) and in each repo for untracked ones. For each,
decide in one line:

- **Keep** — it answers a question that will come back (a console sweep of the
  live sites, a phone-width fit check, a CDP or Playwright walk of a flow). It
  goes into the repo it serves, under `scripts/` or beside the package, with a
  docstring stating its contract and no session paths or credentials baked in.
- **Fold** — it duplicates an existing script or skill step; say which, and
  improve that one instead if the session's version is better.
- **Drop** — a one-off (a single data fix, a probe of one bug).

Propose the list; write the kept ones only after the owner agrees.

## 3. Follow-up docs match reality

For each repo's `PENDING.md` (and lillorepo's `parked-work.md`, android's
`docs/plans/`):

- Strike lines the session's merged PRs closed, citing the PR.
- Add what the session left open, one line each, with its marker (👤 owner,
  ⏳ date or dependency, 🔨 ready, 🚧 blocked) and where the detail lives.
- **Check before keeping a line open**: read the code or the live site. A line
  can describe work that shipped months ago; one did.
- Update dates that moved, and anything an outside notice changed (a provider
  closing, a price, a deadline).

## 4. Pull the vendored skills

In lillorepo, run the three syncs and review each diff before committing:

```bash
bash scripts/sync-google-skills.sh sync          # .claude/skills/google-*  (asks before each overwrite)
bash scripts/sync-web-guidance.sh                # system/skills/modern-web-guidance
bash scripts/sync-anthropic-skills.sh            # system/skills/frontend-design, webapp-testing
bash scripts/install-system.sh                   # system/ → ~/.claude/
```

Say what changed upstream in a line per skill (version, what the guidance now
says differently). Nothing changed is a valid result.

## 5. Release notes

For each package with a `release-notes.md` (lillorepo `packages/*`, and each
android app's), compare its newest entry's date with the user-facing PRs merged
since. If any exist, offer an entry through the `release-notes` skill, drafted
for whoever uses the site or app, and write it only after the owner approves the
text. Internal changes (CI, docs, refactors) do not earn an entry on their own.

## 6. Memory

Update the auto-memory only with what the repos cannot hold: the owner's current
order of work, which repos are paused and why, permissions given for this kind
of work. Prune memory lines the session made wrong.

## 7. Report

One line per step, with its status (done, nothing to do, waiting on the owner)
and its PR when there is one, then what is left in each repo, in a table.

## Growing

New checks join as numbered steps above step 7, each with what it inspects and
what it changes. The intended next one: if the repos come to hold a graph of
their knowledge (decisions, dependencies between packages, who-waits-on-what),
a step that brings that graph in line with the merged PRs, as step 3 does for
the follow-up docs. Until a graph exists, the follow-up docs are the record.
