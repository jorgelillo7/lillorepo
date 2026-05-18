# Python lint & format

This repo uses **flake8** (linter) and **black** (formatter). Both run as a
GitHub Actions job on every push to `master`; the build fails if either
reports issues.

## How it works

Lint runs through Bazel's hermetic Python 3.13 toolchain so local devs and
CI are guaranteed to use the same interpreter and the same `black` /
`flake8` versions resolved by `requirements_lock.txt`.

Two thin Bazel targets in `tools/lint/BUILD.bazel`:

```python
py_console_script_binary(name = "black",  pkg = "@pypi//black")
py_console_script_binary(name = "flake8", pkg = "@pypi//flake8")
```

A wrapper script `scripts/lint.sh` runs both with the right paths:

```bash
bash scripts/lint.sh         # check (what CI runs)
bash scripts/lint.sh --fix   # apply black in place
```

CI calls the same script (`.github/workflows/deploy.yml` → `lint` job).

## Why hermetic

Before this setup, the maintainer ran lint on Python 3.12 locally while CI
used 3.13. Black 26.3.1's wrapping heuristics shift subtly across Python
versions, which caused multiple "passes locally, fails on CI" fixup
commits during the v6.0 refactor. The hermetic Bazel toolchain removes
the drift entirely.

## Pinned versions

The lockfile is the source of truth. As of this writing:

```
black==26.3.1
flake8==7.3.0
```

To upgrade: edit `core/requirements.txt`, regenerate `requirements.in` and
`requirements_lock.txt` (see [`operations.md`](../operations.md)), and
push. Bazel will pick up the new versions automatically on the next lint
invocation. No manual `pip install` step anywhere.

## Editor integration

The shipped `.vscode/settings.json` enables:

- `python.linting.flake8Enabled: true` — flake8 squiggles in the gutter.
- `editor.defaultFormatter: ms-python.black-formatter` + `formatOnSave` —
  Black runs automatically on every save.
- `editor.codeActionsOnSave: { "source.fixAll": "explicit" }` — auto-fix
  available on save.

Required VS Code extensions:

- `ms-python.python`
- `ms-python.black-formatter`

Editor extensions use their own bundled tools, so they may drift from
`scripts/lint.sh` slightly — the final word is what CI says.

## Known gotchas

- **Line-length 88** is the only deviation from PEP 8. Any longer line
  needs to be either reformatted or split — Black handles most cases, but
  long mocked attribute chains in tests are best refactored to an
  intermediate variable rather than suppressed.
- **Don't add `# noqa`** unless there is no clean alternative. Document
  the reason on the same line if you must.
- The repo uses `flake8`'s default ruleset minus `E203` and `W503` (both
  conflict with Black).
