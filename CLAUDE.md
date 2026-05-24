# CLAUDE.md — lillorepo

Bazel monorepo with Python projects targeting Google Cloud. Currently contains `biwenger_tools`; the architecture is designed to grow with more packages.

## Structure

```
/core           Shared libraries (Biwenger SDK, JP SDK, GCP, Telegram; domain models; utils)
/packages       Self-contained projects
  biwenger_tools/
    api/            Flask service exposing the Biwenger business logic over HTTP
    bot/            Telegram bot service — webhooks → calls api
    scraper_job/    League message scraper → CSV → Google Drive
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
bazel test //packages/biwenger_tools/api:api_tests --test_output=streamed --test_arg=-v
bazel test //packages/biwenger_tools/bot:bot_tests --test_output=streamed --test_arg=-v
bazel test //core:core_tests --test_output=streamed --test_arg=-v

# Run locally
bazel run //packages/biwenger_tools/web:web_local
bazel run //packages/biwenger_tools/scraper_job:scraper_job_local
bazel run //packages/biwenger_tools/api:api_local
bazel run //packages/biwenger_tools/bot:bot_local

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

**Never bundle dependency bumps with a feature PR.** Dep upgrades change the runtime
behaviour of the whole image; mixing them with feature code makes regressions
harder to bisect. Ship dep bumps in their own short-lived PR (one bump per PR if
practical) so the deploy that introduces them is reversible without losing the
feature.

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
starting a non-trivial task, deleted once the work is merged. Between sessions the
directory should be empty (and may not exist — create on demand).

Lifecycle:
1. **Create** — write the plan before starting implementation
2. **Use** — reference it during the session; update it if the approach changes
3. **Delete** — once the feature is merged to master, delete the plan file

Do not accumulate stale plans. If a plan describes work that was never started and is
still relevant, keep it. If the code exists and works, the plan is redundant — delete it.

## Pending work

Long-running follow-ups that don't yet warrant a plan or PR. Keep this list short;
remove items when they ship or stop being relevant. For "what has shipped", read
`packages/biwenger_tools/release-notes.md` — single source of truth.

- **Drive folder cleanup** (USER-OWNED, week of 2026-05-26) — when the league ends:
  delete the Drive folder contents (the old CSVs the scraper used to upload), then
  drop the `biwenger-tools-sa-regional` secret or repoint it to a Sheets-only SA
  (Sheets API still authenticates through that mount for `ligas_especiales` /
  `trofeos`).
- **Move Drive/Sheets IDs out of BUILD.bazel** — Sheets IDs (`LIGAS_ESPECIALES_*`,
  `TROFEOS_*`) are still hardcoded in `packages/biwenger_tools/web/BUILD.bazel`.
  Env-var them when convenient. Low priority.
- **Photo-recognition project** — tracked in `packages/my_photos/README.md`, not
  here.

## Memory

Claude Code persistent memory for this project lives at:
`~/.claude/projects/-Users-jorge-Projects-lillorepo/memory/`

Index file: `MEMORY.md`. Each memory is a separate `.md` file in the same directory.

## Notes for Claude

- This repo grows with new packages under `/packages/`. When adding one, replicate the `biwenger_tools` structure as a reference.
- `BUILD.bazel` files are the source of truth for Bazel dependencies.
- See `AGENTS.md` for context on project agents.
- **Commits and PRs:** always write commit messages and PR titles/descriptions in English. Do not add a `Co-Authored-By` line.
- **Web UI design system:** see `packages/biwenger_tools/web/DESIGN.md` before touching templates — it defines the canonical color tokens, typography, and component rules.
