# Python lint & format

This repo uses **flake8** (linter) and **black** (formatter). Both run as a
GitHub Actions job on every push to `master`; the build fails if either
reports issues.

## What was already in the repo

- **`.flake8`** at repo root — `max-line-length = 88`, ignores `E203, W503`
  (Black-compatible defaults).
- **`.vscode/settings.json`** — enables flake8 + Black-on-save in the editor.
- **`core/requirements.txt`** lists `flake8` and `black` as dev tooling, so
  both are pinned in `requirements_lock.txt`.

The editor side worked out of the box because the VS Code extensions ship
their own bundled tools; what was missing was a CLI / CI path.

## What was added

| Change | Where |
|--------|-------|
| New CI job `lint` (flake8 + `black --check`) before `test` | `.github/workflows/deploy.yml` |
| Pinned tool versions documented and aligned with `requirements_lock.txt` | this file + workflow comment |
| Cleanup pass (E501 line-length, F401 unused imports, F541 empty f-strings) so the lint step starts green | various files |

## Pinned versions

The lockfile is the source of truth. As of this writing:

```
flake8==7.3.0
black==25.1.0
```

The CI step pins these explicitly. **Bump both the workflow and the
lockfile in the same PR** when upgrading; otherwise a regen of
`requirements_lock.txt` will drift from CI.

## Running locally

```bash
# One-time install (matches CI versions)
pip3 install flake8==7.3.0 black==25.1.0

# Lint
flake8 core/ packages/

# Format check (read-only — same as CI)
black --check core/ packages/

# Format in place
black core/ packages/
```

## Editor integration

The `.vscode/settings.json` already shipped enables:

- `python.linting.flake8Enabled: true` — flake8 squiggles in the gutter.
- `editor.defaultFormatter: ms-python.black-formatter` + `formatOnSave` —
  Black runs automatically on every save.
- `editor.codeActionsOnSave: { "source.fixAll": "explicit" }` — auto-fix
  available on save.

Required VS Code extensions:

- `ms-python.python`
- `ms-python.black-formatter`

## CI behavior

`.github/workflows/deploy.yml` runs the workflow only when paths under
`core/`, `packages/biwenger_tools/{web,scraper_job}/`, `tools/` or the
workflow itself change. Within that scope the dependency chain is:

```
lint ──► test ──► deploy-web / deploy-scraper
```

A lint failure blocks `test`, which in turn blocks the deploy. Lint
finishes in seconds (no Bazel needed), so it acts as a fast pre-flight.

## Known gotchas

- **Line-length 88** is the only deviation from PEP 8. Any longer line
  needs to be either reformatted or split — Black handles most cases, but
  long mocked attribute chains in tests (e.g. `mock.x.y.z.return_value...`)
  are best refactored to an intermediate variable rather than suppressed.
- **Don't add `# noqa`** unless there is no clean alternative. Document
  the reason on the same line if you must.
- The repo uses `flake8`'s default ruleset minus `E203` and `W503` (both
  conflict with Black). Adding new ignores should be discussed in the PR.
