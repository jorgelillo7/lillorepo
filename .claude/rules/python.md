---
paths:
  - "**/*.py"
  - "**/BUILD.bazel"
  - "**/requirements*.txt"
  - "requirements.in"
  - "requirements_lock.txt"
  - "MODULE.bazel"
---

# Python in lillorepo

## The conventions (LP-1 … LP-24)

`docs/technical/backend/python-conventions.md` holds every rule with its motive
and how it is checked (CI or review). **Read it before writing new Python.**
The titles, so you know which one to look up:

| | Dependencies | | Code shape and failures |
|---|---|---|---|
| LP-1 | One resolution point | LP-7 | Four layers, and the draft is the canon |
| LP-2 | Every consumed distribution is declared directly | LP-8 | Functions and dataclasses before classes |
| LP-3 | The lock is generated; the image list is derived | LP-9 | Shared code is a Bazel dependency, never a path |
| LP-4 | A dependency change ships alone | LP-10 | `core` holds only what genuinely crosses packages |
| LP-5 | Development environments derive from the lock | LP-11 | Loud beats silent |
| LP-6 | `requests` and the stdlib first | LP-12 | Never retry a non-idempotent mutation |
| | | LP-13 | Idempotency is built on our side, and writes are verified |
| | | LP-14 | Every error reaches the person who asked |

| | Observability and docs | | Tests |
|---|---|---|---|
| LP-15 | Structured logs, data in `extra` | LP-18 | The test comes first, and is seen failing (`logic/` and `core/`) |
| LP-16 | Docstrings state contracts, types state shapes | LP-19 | Every module has a suite, and CI runs it |
| LP-17 | Spanish for users, English for everything else | LP-20 | A spec and its test are a pair |
| | | LP-21 | Mock at the boundary; never the network |
| | | LP-22 | Every path that moves money has a duplicate-call test |
| | | LP-23 | One quality toolchain, run hermetically |
| | | LP-24 | Scripts are dry-run by default |

## Dependencies

Three levels: `[module]/requirements.txt` → `requirements.in` (generated) →
`requirements_lock.txt` (the Bazel lock). Never edit the last two by hand:

1. Edit `[module]/requirements.txt`.
2. Regenerate `requirements.in` with the concatenation script.
3. `venv/bin/pip-compile requirements.in -o requirements_lock.txt` on Python
   3.14 with `pip-tools==7.6.1` and `CUSTOM_COMPILE_COMMAND` — exact command in
   `docs/operations.md`. The `add-python-dep` skill walks all five layers.
4. Add the dependency to the module's `BUILD.bazel` (`@pypi//library_name`;
   hyphens in PyPI names become underscores).

**A dependency bump never rides with a feature PR.** It changes the runtime of
the whole image; on its own, the deploy that introduces it can be reverted
without losing the feature.

## Running and checking

- **Scripts run on the lock, never on the Mac's Python.** The system `python3`
  carries stale packages (requests 2.28 / urllib3 1.26) that some providers
  reject: use a `bazel run` target, or a venv built from
  `requirements_lock.txt` on Python 3.14 for one-off scripts. What that
  breaks in `biwenger_tools` (Oráculo) is in its `.claude/CLAUDE.md`.
- Format, lint and import order: Ruff (`ruff.toml`, 88 columns); types: mypy
  over the trees in `mypy.ini`. Both from the lock through `scripts/lint.sh`.
- `BUILD.bazel` files are the source of truth for Bazel dependencies; targets
  follow `//packages/{package}/{module}:{target}`.
