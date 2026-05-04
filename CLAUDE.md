# CLAUDE.md — lillorepo

Bazel monorepo with Python projects targeting Google Cloud. Currently contains `biwenger_tools`; the architecture is designed to grow with more packages.

## Structure

```
/core           Shared libraries (Biwenger SDK, JP SDK, GCP, Telegram; domain models; utils)
/packages       Self-contained projects
  biwenger_tools/
    scraper_job/    League message scraper → CSV → Google Drive
    teams_analyzer/ Biwenger squad + market analysis enriched with JP predictions → Telegram messages
    web/            Flask app on Cloud Run for data visualisation
/docker         Docker configurations
/docs           Documentation (operations.md = command reference, setup/linter.md = lint/format)
/scripts        Utility scripts (GCP cleanup, costs)
/tools          Bazel extensions and tools
/platforms      Platform definitions (linux_amd64, etc.)
```

## Stack

- **Build:** Bazel (bazelisk)
- **Language:** Python 3.12
- **Cloud:** GCP — Cloud Run, Cloud Run Jobs, Secret Manager, Artifact Registry
- **Other:** Flask, Docker
- **CI:** GitHub Actions runs flake8 + `black --check` before tests; tests gate the deploy.

## Key Commands

See `docs/operations.md` for the full reference. Quick summary:

```bash
# Full build
bazel build //...

# Tests (any module)
bazel test //packages/biwenger_tools/web:web_tests --test_output=streamed --test_arg=-v
bazel test //packages/biwenger_tools/scraper_job:scraper_job_tests --test_output=streamed --test_arg=-v
bazel test //packages/biwenger_tools/teams_analyzer:teams_analyzer_tests --test_output=streamed --test_arg=-v
bazel test //core:core_tests --test_output=streamed --test_arg=-v

# Run locally
bazel run //packages/biwenger_tools/web:web_local
bazel run //packages/biwenger_tools/scraper_job:scraper_job_local
bazel run //packages/biwenger_tools/teams_analyzer:teams_analyzer_local

# Deploy (web)
bazel run //packages/biwenger_tools/web:push_image_to_gcp --platforms=//platforms:linux_amd64
cd packages/biwenger_tools/web/ && ./deploy.sh
```

## Python Dependency Management

Three-level system: `[module]/requirements.txt` → `requirements.in` (auto-generated) → `requirements_lock.txt` (Bazel lock file).

Never edit `requirements.in` or `requirements_lock.txt` by hand. Workflow:
1. Edit `[module]/requirements.txt`
2. Regenerate `requirements.in` with the concatenation script
3. `pip-compile requirements.in -o requirements_lock.txt`
4. Add the dep in the module's `BUILD.bazel` (`@pypi//library_name`)

## Secrets

- **Local:** `.env` files in each module (do not commit)
- **Production:** Google Secret Manager

## Conventions

- Linter: Flake8 (`max-line-length = 88`, compatible with Black)
- Formatter: Black (format on save in VS Code)
- Bazel targets follow the pattern `//packages/{package}/{module}:{target}`
- Hyphens in PyPI library names become underscores in Bazel (`@pypi//library_name`)

## Branch and PR Workflow

This repo deploys to production on every push to `master` (see `.github/workflows/deploy.yml`).
**Always work on a feature branch and open a PR** — never commit directly to master.

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

For quick fixes or documentation-only changes, a short-lived branch + immediate PR merge is still preferred over committing directly.

## Plans (`.claude/plans/`)

Implementation plans live in `.claude/plans/`. They are session-scoped: created before
starting a non-trivial task, deleted once the work is merged.

Lifecycle:
1. **Create** — write the plan before starting implementation
2. **Use** — reference it during the session; update it if the approach changes
3. **Delete** — once the feature is merged to master, delete the plan file

Do not accumulate stale plans. If a plan describes work that was never started and is
still relevant, keep it. If the code exists and works, the plan is redundant — delete it.

Current active plans: `.claude/plans/teams_analyzer_rewrite.md`

## Memory

Claude Code persistent memory for this project lives at:
`~/.claude/projects/-Users-jorge-Projects-lillorepo/memory/`

Index file: `MEMORY.md`. Each memory is a separate `.md` file in the same directory.

## Notes for Claude

- This repo grows with new packages under `/packages/`. When adding one, replicate the `biwenger_tools` structure as a reference.
- `BUILD.bazel` files are the source of truth for Bazel dependencies.
- See `AGENTS.md` for context on project agents.
- **Commits:** always write commit messages in English. Do not add a `Co-Authored-By` line.
- **Web UI design system:** see `packages/biwenger_tools/web/DESIGN.md` before touching templates — it defines the canonical color tokens, typography, and component rules.
