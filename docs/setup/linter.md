# Python lint & format

This repo uses **Ruff** for all three jobs that used to take three tools:

| Job | Ruff | Replaces |
|---|---|---|
| Formatting | `ruff format` | black |
| Linting (`E`, `W`, `F`) | `ruff check` | flake8 |
| Import order (`I`) | `ruff check` | isort (never used before) |

It runs as the required `Lint` check on every pull request, and again on every
push to `master`; the build fails if it reports anything.

## Types: mypy

`mypy.ini` decides what is type-checked: the trees under `files` — a tree joins
once it is clean, and stays clean. That is every package now: `core`,
`packages/*` (tests excluded). `scripts/lint.sh` runs it
as `//tools/lint:mypy`, in-process, with the runtime libraries the code imports
plus the stubs for those that ship none (`types-bleach`, `types-gunicorn`,
`types-python-dateutil`) as Bazel deps — so it reads their real types. A new
third-party import must be added to those deps — and only then: the deps are
kept to what the checked trees import, because every wheel adds thousands of
files Bazel lays out on each CI run. One with no types and no stubs (today
`googleapiclient`, `google.auth`) is ignored **by name** in `mypy.ini`. Its
cache lives in `.mypy_cache/` (git-ignored); CI keeps it between runs with
`actions/cache`, keyed on the lock and `mypy.ini`.

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

Configuration lives in `ruff.toml` at the repo root: 88 columns, Python 3.13
syntax (see the gotcha below),
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
- **Ruff formats for Python 3.13 syntax** (`target-version = "py313"`) though
  the code runs on 3.14. Targeting 3.14 made it strip the parentheses from
  `except (A, B):` — valid only on 3.14, and it reads like Python 2's very
  different `except A, B:`. Ten files shipped like that once.
- **Ruff joins adjacent string literals.** `"…?auth" "=abc"` becomes one
  string on the next format. A string split on purpose — so a file does not
  itself hold a literal credential URL, say — must be built another way (a
  variable, an f-string); a split string does not survive.
- `bash scripts/lint.sh --fix` formats even when `ruff check` leaves an error
  it cannot fix itself (a long line); the error is still the exit code.
