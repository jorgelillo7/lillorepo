# CLAUDE.md — lillorepo

Bazel monorepo with Python projects targeting Google Cloud: four packages —
`biwenger_tools`, `be_water`, `chucknorris_bot` and `my_photos` (plan only) —
over one shared `core`.

## Ground rules

Three habits that cost real time when they were missing. Each one is here
because it went wrong, not because it sounds sensible.

- **Never say something does not exist from memory.** Versions, model names,
  package releases, API capabilities — check first (`WebSearch`, `npm view`,
  `brew info`, `gcloud components list`). Two separate sessions were spent
  insisting "Opus 5" was not a real model until a screenshot forced a search;
  the actual cause was a Homebrew cask lagging behind npm. The user's
  information about a moving target is newer than the model's, always.

- **Restate a list before working it, and account for every line at the end.**
  Given a review, a set of `PENDING.md` items or any backlog, echo it as a
  checklist first and close with the status of each item. Stopping after the
  first few and reporting done has happened more than once, and it is invisible
  to whoever asked.

- **Everything written down is in English** — READMEs, runbooks, release notes,
  specs, code comments, commit messages, PR descriptions — regardless of the
  language of the conversation. A README once shipped in Spanish against this
  rule and had to be rewritten.

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

## Python Dependency Management

Three-level system: `[module]/requirements.txt` → `requirements.in` (auto-generated) → `requirements_lock.txt` (Bazel lock file).

Never edit `requirements.in` or `requirements_lock.txt` by hand. Workflow:
1. Edit `[module]/requirements.txt`
2. Regenerate `requirements.in` with the concatenation script
3. `venv/bin/pip-compile requirements.in -o requirements_lock.txt` on Python 3.14 with `pip-tools==7.6.1` and `CUSTOM_COMPILE_COMMAND` — exact command in `docs/operations.md`
4. Add the dep in the module's `BUILD.bazel` (`@pypi//library_name`)

**Never bundle dependency bumps with a feature PR.** Dep upgrades change the runtime
behaviour of the whole image; mixing them with feature code makes regressions
harder to bisect. Ship dep bumps in their own short-lived PR (one bump per PR if
practical) so the deploy that introduces them is reversible without losing the
feature.

## Secrets

- **Local:** `.env` files in each module (do not commit)
- **Production:** Google Secret Manager

## Conventions

- **Python conventions of this repo:** `docs/technical/backend/python-conventions.md`
  — layer rules (pure logic / service / thin route / zero-logic bot), the
  loud-failure and no-retry policies, the test-first loop (LP-18: for `logic/` and
  `core/`, the test is written and observed failing before the code), testing
  patterns and stack traps. Rules are numbered `LP-1` … `LP-24`, each with its
  motive and how it is checked (CI or review).
  Read it before writing new Python.
- Format, lint and import order: Ruff (`ruff.toml`, 88 columns); types: mypy
  over the trees in `mypy.ini` (gradual). Both from the lock through
  `scripts/lint.sh`; format on save in VS Code
- Bazel targets follow the pattern `//packages/{package}/{module}:{target}`
- Hyphens in PyPI library names become underscores in Bazel (`@pypi//library_name`)
- **Commit scopes use the exact package directory name** — with multiple
  packages, a bare `feat(web):` is ambiguous, and abbreviations drift.
  The scope is the directory under `/packages/`: `feat(be_water):`,
  `fix(biwenger_tools):` (module-qualified when it helps:
  `fix(biwenger_tools/api):`), `feat(chucknorris_bot):`. Cross-cutting
  scopes stay as-is: `(core)`, `(ci)`, `(deps)`, plain `docs:`/`chore:`
  for repo-wide changes.
- **PRs merge via squash only** (enforced in repo settings): one commit
  per PR, commit title = PR title, body = the branch's commit messages.
  Keeps `git log --oneline` reading as the project history.

## Branch and PR Workflow

This repo deploys to production on every push to `master` (see `.github/workflows/deploy.yml`).
**Always work on a feature branch and open a PR** — never commit directly to master.

**No exceptions.** Every change — docs, comments, CLAUDE.md edits, README
typos, urgent hotfixes — goes through branch + PR + green checks + merge.
There is no "commit directly to master" authorisation, from anyone, ever.
If it's urgent, the fast path is the same path: branch, PR, wait for `Lint`
and `Test`, merge.

This is enforced, not just policy: `master` has branch protection (required
status checks `Lint` + `Test` from `ci.yml`, `enforce_admins` on, no
force-pushes). A direct push is rejected by GitHub regardless of intent.

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

## Service-level objectives

Single SLO covers the user-facing surface of the project:

- **Daily 09:00 Madrid digest end-to-end ≤ 5 min.** The Cloud Scheduler tick
  fires `/digests/daily`, which chains: JP fetch + Biwenger session + market
  read + N bids + Firestore log writes + 2 Telegram photos + 1 Telegram
  summary. Each component has its own timeouts; the SLO is the wall-clock
  total observed end-to-end. Burns: any run that exceeds 5 min, or any
  morning where the summary fails to arrive, counts against the budget.

What this implies in practice:
- Cloud Run min-instances=0 cold start is part of the budget — currently
  ~5-10 s thanks to the pre-compiled `python-base` image. Drift here is
  worth investigating.
- Biwenger flake / JP cache miss budget is ~30 s combined; the rest of the
  5 min is comfort headroom.
- There is no automated alerting (deliberate, see `STATUS.md` "Accepted
  gaps"). The SLO is enforced by the user checking whether the morning
  message arrived; missed mornings get diagnosed manually in Cloud Logging.

## Memory

Claude Code persistent memory for this project lives at:
`~/.claude/projects/-Users-jorge-Projects-lillorepo/memory/`

Index file: `MEMORY.md`. Each memory is a separate `.md` file in the same directory.

## Notes for Claude

- This repo grows with new packages under `/packages/`. When adding one, replicate the `biwenger_tools` structure as a reference.
- **Skills are scoped.** `/.claude/skills/` holds only what would make sense in a repo that had never heard of Biwenger; anything domain-specific lives in its package (`packages/biwenger_tools/.claude/skills/`), and Claude Code prefers the scoped one when you work inside that package. Each `.claude/CLAUDE.md` indexes its own.
- `BUILD.bazel` files are the source of truth for Bazel dependencies.
- **Subagent roles** live in `.claude/agents/` (`dev`, `qa`, `reviewer`,
  `spec`) — what each is for, and what delegating to one does and does not
  buy, is in `AGENTS.md`.
- **Commits and PRs:** always write commit messages and PR titles/descriptions in English. Do not add a `Co-Authored-By` line.
- **Web UI design system:** see `packages/biwenger_tools/web/DESIGN.md` before touching templates — it defines the canonical color tokens, typography, and component rules.
