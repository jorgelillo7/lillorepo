# Python lint & format

This repo uses **Ruff** for all three jobs that used to take three tools:

| Job | Ruff | Replaces |
|---|---|---|
| Formatting | `ruff format` | black |
| Linting (`E`, `W`, `F`) | `ruff check` | flake8 |
| Import order (`I`) | `ruff check` | isort (never used before) |

It runs as the required `Lint` check on every pull request, and again on every
push to `master`; the build fails if it reports anything.

## How it works

Ruff runs through Bazel at the version `requirements_lock.txt` pins, so the
Mac and CI use the same binary (python-conventions LP-23). Its wheel ships a
compiled binary and no console-script entry point, so `tools/lint/BUILD.bazel`
exposes it with a small rule, `whl_bin` (`tools/lint/whl_bin.bzl`), that picks
`bin/ruff` out of `@pypi//ruff:data`.

The wrapper is the single entry point:

```bash
bash scripts/lint.sh         # check — what CI runs
bash scripts/lint.sh --fix   # sort imports, autofix, then format in place
```

Configuration lives in `ruff.toml` at the repo root: 88 columns, Python 3.14,
rules `E`, `W`, `F`, `I` (minus `E203`), `core` and `packages` as first-party
imports. A nested config, if one is ever needed, must
`extend = "../ruff.toml"` — without it, it inherits nothing from the root.

## Upgrading

`ruff` is a dev-only dependency in `core/requirements.txt`. Regenerate
`requirements.in` and the lock (see [`operations.md`](../operations.md)),
open the bump as its own pull request (LP-4), and run
`bash scripts/lint.sh --fix` in it: a new Ruff can format a few lines
differently.

## `git blame`

The switch to Ruff reformatted ~70 files in one commit. Skip it in blame:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

## Editor integration

`.vscode/settings.json` sets the Ruff extension (`charliermarsh.ruff`) as the
Python formatter, formats on save, and fixes and organises imports on save. The
extension bundles its own Ruff; CI's lock-pinned one is the final word.

## Known gotchas

- **Line length 88.** Any longer line needs reformatting or splitting; long
  mocked attribute chains in tests are better refactored to an intermediate
  variable than suppressed.
- **Don't add `# noqa`** unless there is no clean alternative, and name the
  rule (`# noqa: F401`) with the reason on the same line.
- `E203` is ignored: it conflicts with the formatter's slices.
