# CLAUDE.md — lillorepo

Bazel monorepo with Python projects targeting Google Cloud — `biwenger_tools`,
`be_water`, `chucknorris_bot`, `group_polls` and `my_photos` (plan only) — over
one shared `core`. Two packages are not Python: `interactive_fiction` (a static
site) and `wishlist` (a Worker with D1) are Node, outside Bazel, each with its
own `npm` workflow (see their READMEs).

A package that is not Python stays outside Bazel: its own toolchain and
lockfile, its own job in `ci.yml` registered as a required check, and its own
runbook. It shares nothing with `core`, so Bazel would add a second dependency
graph and no caching worth having.

Personal habits that hold in every repo — Spanish in the conversation and
English in everything written, checking before saying something does not
exist, working a list whole, comments without history, the git and PR
habits — are rules in `~/.claude/rules/`, versioned in
[`system/rules/`](system/rules/) and installed by `scripts/install-system.sh`.
A session that cannot read `~/.claude/` (a cloud session) reads them there.
Python rules load from `.claude/rules/python.md` when a Python file is opened.

## Structure

```
/core           Shared libraries (Biwenger SDK, JP SDK, GCP, Telegram; domain models; utils)
/packages       Self-contained projects (the table in README.md is the inventory)
  biwenger_tools/   Fantasy-league platform: api, bot, scraper_job, web
  be_water/         Bottled-water catalog (own GCP project be-water-app): web, scripts
  chucknorris_bot/  Telegram joke bot
  my_photos/        Plan only, no code
/docker         Docker configurations
/infra          Terraform for the static GCP layer of both projects (see infra/README.md)
/docs           Documentation (operations.md = repo-wide runbook + index; per-package commands in packages/*/OPERATIONS.md; setup/linter.md = lint/format; personal/ = non-code personal notes, the one place Spanish is allowed)
/openspec       Behaviour specs — the canonical source of project decisions (see "Specs")
/scripts        Utility scripts (GCP cleanup, costs)
/system         Personal skills and rules, installed into ~/.claude/ (see .claude/CLAUDE.md)
/tools          Bazel extensions and tools
/platforms      Platform definitions (linux_amd64, etc.)
```

## Stack

- **Build:** Bazel (bazelisk)
- **Language:** Python 3.14
- **Cloud:** GCP — Cloud Run, Cloud Run Jobs, Secret Manager, Artifact Registry
- **Other:** Flask, Docker
- **CI:** GitHub Actions runs Ruff (format check + lint) before tests; tests gate the deploy.

## Key Commands

Per-package run/deploy commands live in `packages/*/OPERATIONS.md`, repo-wide
workflows in `docs/operations.md`. What every session needs:

```bash
bash scripts/lint.sh                                  # what CI's Lint job runs
bazel test --build_tests_only //...                   # every suite
bazel query 'tests(//...)'                            # the suites that exist
bazel test //<package path>:<suite> --test_output=errors
python3 scripts/affected_tests.py origin/master       # what CI would run here
```

## Secrets

- **Local:** `.env` files in each module (do not commit)
- **Production:** Google Secret Manager

## Conventions

- **Python:** conventions LP-1 … LP-24 in
  `docs/technical/backend/python-conventions.md`; dependencies, the lock and
  the toolchain in `.claude/rules/python.md`, which loads with any Python
  file.
- **Commit scopes use the exact package directory name** — with multiple
  packages, a bare `feat(web):` is ambiguous, and abbreviations drift.
  The scope is the directory under `/packages/`: `feat(be_water):`,
  `fix(biwenger_tools):` (module-qualified when it helps:
  `fix(biwenger_tools/api):`), `feat(chucknorris_bot):`. Cross-cutting
  scopes stay as-is: `(core)`, `(ci)`, `(deps)`, plain `docs:`/`chore:`
  for repo-wide changes.
- **PRs merge via squash only**, enforced in the repo settings.

## Branch and PR Workflow

This repo deploys to production on every push to `master` (see `.github/workflows/deploy.yml`).
**Always work on a feature branch and open a PR** — never commit directly to master.

**No exceptions.** Every change — docs, comments, CLAUDE.md edits, README
typos, urgent hotfixes — goes through branch + PR + green checks + merge.
There is no "commit directly to master" authorisation, from anyone, ever.
If it's urgent, the fast path is the same path: branch, PR, wait for the
required checks, merge.

This is enforced, not just policy: `master` has branch protection (required
status checks `Lint`, `Test` and `Interactive fiction` from `ci.yml`, branches up to date with
`master` before merging, `enforce_admins` on, no force-pushes). A direct push is rejected by GitHub regardless of intent.

```bash
git checkout -b feat/my-feature
# ... do work ...
git push -u origin feat/my-feature
gh pr create --title "..." --body "..."
```

Rationale:
- The CI pipeline on `master` triggers real deploys to Cloud Run — a broken commit ships broken code.
- GitHub Actions is free for public repos, so cost is not the concern; correctness is.
- PRs give a natural review checkpoint and keep master always deployable.

For quick fixes or documentation-only changes, use a short-lived branch + immediate PR merge once checks are green.

### Merging and shipping: the `ship` skill

Every merge goes through `.claude/skills/ship/SKILL.md`. It holds the three
traps that each cost a broken `master` or a lost PR once: merge only the head
that GitHub checked (`git rev-parse HEAD` = `origin/<branch>`); never merge a
base with `--delete-branch` while a PR is stacked on it (branch off `master`
instead); and a merge is not a deploy — watch the `deploy.yml` run and confirm
the revisions serve, in **both** GCP projects (`be_water` is `be-water-app`).

## Specs (`openspec/`)

`openspec/` is the canonical, tool-agnostic home for **project decisions and
behaviour** — the single source of *what the system must do*. The goal is that
every non-trivial decision ends up here, not scattered across docstrings,
memory, and OPERATIONS docs. New sessions should read `openspec/project.md`
first for the behaviour map.

- **`openspec/project.md`** — the repo behaviour map + index of capabilities.
- **`openspec/specs/{package}/{capability}/spec.md`** — current behaviour,
  grouped by the package it belongs to (`biwenger_tools`, `be_water`,
  `chucknorris_bot`, `core`), stated as `Requirement` (SHALL) + `Scenario`
  (WHEN/THEN) blocks. Each scenario links the test that verifies it.
- **`openspec/changes/{name}/`** — in-flight proposals (`proposal.md`,
  `design.md`, `tasks.md`, spec deltas); empty between changes.

Spec vs test: the spec states the **what**, the test proves **it holds**. They
are complementary, never duplicated — a scenario with no test is a gap; a test
with no scenario is undocumented behaviour. When you change behaviour, update
the spec in the same PR. Follows the [OpenSpec](https://github.com/Fission-AI/OpenSpec)
filesystem convention (convention only — no npm CLI).

## Plans (`.claude/plans/`)

Implementation plans live in `.claude/plans/`. They are session-scoped: created before
starting a non-trivial task, deleted once the work is merged. Between sessions the
directory should be empty (and may not exist — create on demand).

Lifecycle:
1. **Create** — write the plan before starting implementation
2. **Use** — reference it during the session; update it if the approach changes
3. **Delete** — once the feature is merged to master, delete the plan file

Do not accumulate stale plans. If a plan describes work that was never started and is
still relevant, keep it. If the code exists and works, the plan is redundant — delete it.

## Pending work

Long-running follow-ups live in `PENDING.md` at the repo root. It is an
**index, not a notebook: one line per item**, grouped by area, with a marker
for whether it needs the owner, waits on a trigger, or is ready to pick up.

If an item needs more than a line, the reasoning goes where it belongs and
`PENDING.md` links to it:

- behaviour and decisions → `openspec/`
- technical evaluations and parked work → `docs/technical/parked-work.md`
- anything else → the PR that closed it, and `git log`

That split exists because the file had grown to 232 lines for 13 items and
stopped being scannable, which is the only job it has. The file is never
deleted; lines get pruned as items ship. For "what has shipped" read
`packages/biwenger_tools/release-notes.md`, and for the state of the repo
`STATUS.md` — neither belongs in `PENDING.md`.

## Notes for Claude

- This repo grows with new packages under `/packages/`. When adding one, replicate the `biwenger_tools` structure as a reference.
- **Skills are scoped.** `/.claude/skills/` holds only what would make sense in a repo that had never heard of Biwenger; anything domain-specific lives in its package (`packages/biwenger_tools/.claude/skills/`), and Claude Code prefers the scoped one when you work inside that package. Each `.claude/CLAUDE.md` indexes its own.
- **Subagent roles** live in `.claude/agents/` (`dev`, `qa`, `reviewer`,
  `spec`) — what each is for, and what delegating to one does and does not
  buy, is in `AGENTS.md`.
- **Web UI design system:** see `packages/biwenger_tools/web/DESIGN.md` before touching templates — it defines the canonical color tokens, typography, and component rules.
