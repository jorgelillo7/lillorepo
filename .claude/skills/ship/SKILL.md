---
name: ship
description: Merge a PR and prove it reached production — checks the pushed head matches local, refuses stacked branches, watches the deploy, and confirms the Cloud Run revisions are serving. Use when a PR is green and ready to merge.
model-invocable: false
allowed-tools:
  - Bash
  - Read
---

# Goal

Turn "the PR is green" into "the change is running", without the three things
that have gone wrong doing this by hand.

This skill does **not** decide whether to merge. It refuses to merge until the
checks are green on the exact commit that is on GitHub.

# Step 1 — The head you are merging is the head that was checked

```bash
git rev-parse HEAD
git rev-parse origin/<branch>
```

**Identical, or stop and push.** Green checks belong to a pushed commit, not to
your working tree. A merge once went through on a branch whose last fix had
never reached GitHub: the checks were green for the *previous* push, and
`master` broke. `gh pr checks` cannot tell you this — it reports on what the
remote has.

# Step 2 — Nothing is stacked on this branch

```bash
gh pr list --base <branch>
```

Must be empty. A stacked PR does get checks now — `ci.yml` triggers on every
pull request and diffs against its own base — but merging this branch with
`--delete-branch` still **closes** it, and a closed PR can be neither reopened
nor retargeted: the work has to be rebased and opened under a new number.

If something is stacked, retarget it to `master` (`gh pr edit <n> --base
master`) **before** merging this one.

# Step 3 — Checks, on that head

```bash
gh pr checks <pr>
```

Both `Lint` and `Test` passing. If a check never appeared, `ci.yml` may not have
fired — re-push or use `gh workflow run`.

# Step 4 — Merge

```bash
gh pr merge <pr> --squash --delete-branch
```

Squash only; the repo enforces it. The commit title becomes the `git log` line.

# Step 5 — Watch the deploy, and know when there isn't one

```bash
gh run list --branch master --limit 1 --json databaseId,status,headSha
gh run watch <id>
```

`deploy.yml` runs on push to master with a per-service `paths-filter`. **A
docs-only change may legitimately deploy nothing** — decide which case you are
in from the paths you touched, or you will wait for a run that is never coming.

# Step 6 — Confirm the revisions are serving

A green workflow is not a running service.

```bash
gcloud run services list --project biwenger-tools --region europe-southwest1 \
  --format="value(metadata.name,status.conditions[0].status,status.latestReadyRevisionName)"
gcloud run services list --project be-water-app --region europe-southwest1 \
  --format="value(metadata.name,status.conditions[0].status)"
```

`be_water` lives in **its own GCP project** — checking only `biwenger-tools`
misses it. Every service must read `True`. A new `latestReadyRevisionName`
means the container actually started, which is the only proof that an import
error or a bad entrypoint did not ship.

For a user-facing change, hit it:

```bash
curl -s -o /dev/null -w "%{http_code}\n" "$(gcloud run services describe biwenger-summary \
  --project biwenger-tools --region europe-southwest1 --format='value(status.url)')"
```

# Step 7 — Master is still healthy

```bash
git checkout master && git pull && bash scripts/lint.sh
```

Catches the case where two PRs were each green alone and not together —
typically a spec naming a test the other branch renamed.

# When it goes wrong

- **No CI run appeared.** GitHub occasionally swallows the webhook. Push an
  empty commit or `gh workflow run ci.yml --ref <branch>`.
- **Deploy failed.** `gh run view <id> --log-failed`. The service keeps serving
  the previous revision, so production is not down — fix forward on a branch.
- **Revision not Ready.** The container did not start. `gcloud logging read`
  filtered to that revision; an `ImportError` here usually means a file the
  Bazel graph has and the image layer does not.

# Rules

- Never merge on checks you have not seen green for the pushed head.
- Never `--delete-branch` while another PR targets this branch.
- "Merged" is not a report. "Serving, revision `X`, lint green" is.
- One command bypasses the local output filter when a result will be parsed:
  `rtk proxy <cmd>` (see `~/.claude/RTK.md`).
