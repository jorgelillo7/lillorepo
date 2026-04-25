# CLAUDE.md — lillorepo

Bazel monorepo with Python projects targeting Google Cloud. Currently contains `biwenger_tools`; the architecture is designed to grow with more packages.

## Structure

```
/core           Shared libraries (Biwenger SDK, GCP, Telegram; utils)
/packages       Self-contained projects
  biwenger_tools/
    scraper_job/    League message scraper → CSV → Google Drive
    teams_analyzer/ Biwenger team analysis → CSV → Telegram
    web/            Flask app on Cloud Run for data visualisation
/docker         Docker configurations
/docs           Documentation (operations.md = command reference)
/scripts        Utility scripts (GCP cleanup, costs)
/tools          Bazel extensions and tools
/platforms      Platform definitions (linux_amd64, etc.)
```

## Stack

- **Build:** Bazel (bazelisk)
- **Language:** Python 3
- **Cloud:** GCP — Cloud Run, Cloud Run Jobs, Secret Manager, Artifact Registry
- **Other:** Flask, Selenium, Docker

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

## Notes for Claude

- This repo grows with new packages under `/packages/`. When adding one, replicate the `biwenger_tools` structure as a reference.
- `BUILD.bazel` files are the source of truth for Bazel dependencies.
- See `AGENTS.md` for context on project agents.
- **Commits:** always write commit messages in English. Do not add a `Co-Authored-By` line.
