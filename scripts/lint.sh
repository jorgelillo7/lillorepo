#!/bin/bash
# Run Ruff hermetically (formatter, linter and import sorter in one tool) with
# the version the lock pins, then the repo's stdlib checks. CI runs exactly
# this script, so a clean local run is a clean Lint job.
#
# Why Bazel: a formatter run with whatever version is on PATH drifts from CI
# and produces fixup commits (python-conventions LP-23).
#
# Usage: bash scripts/lint.sh           # check core/ and packages/
#        bash scripts/lint.sh --fix     # sort imports, autofix, format in place
#
# First invocation is slow (Bazel resolves the lint target); later ones use
# the cache.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TARGETS=("core/" "packages/")
RUFF=(bazel run --ui_event_filters=-info,-stdout,-stderr //tools/lint:ruff --)

if [[ "${1:-}" == "--fix" ]]; then
    # Format even when `check` leaves something it cannot fix on its own (a
    # long line, say): formatting often resolves exactly that. Its status is
    # still the script's exit code, so what remains is not hidden.
    echo "==> ruff check --fix…"
    status=0
    "${RUFF[@]}" check --fix --config "$REPO_ROOT/ruff.toml" \
        "${TARGETS[@]/#/$REPO_ROOT/}" || status=$?
    echo "==> ruff format…"
    "${RUFF[@]}" format --config "$REPO_ROOT/ruff.toml" "${TARGETS[@]/#/$REPO_ROOT/}"
    exit "$status"
fi

echo "==> ruff format --check…"
"${RUFF[@]}" format --check --config "$REPO_ROOT/ruff.toml" "${TARGETS[@]/#/$REPO_ROOT/}"

echo "==> ruff check…"
"${RUFF[@]}" check --config "$REPO_ROOT/ruff.toml" "${TARGETS[@]/#/$REPO_ROOT/}"

# Types, gradually: mypy checks the trees `mypy.ini` lists under `files`, at
# the lock's version, against the real types of the libraries they import.
echo "==> mypy…"
bazel run --ui_event_filters=-info,-stdout,-stderr //tools/lint:mypy -- \
    --config-file "$REPO_ROOT/mypy.ini" --cache-dir "$REPO_ROOT/.mypy_cache"

# Stdlib-only and offline, so it costs ~1 s and needs no toolchain. Guards the
# gap the linters cannot see: Bazel tests run against requirements_lock.txt
# while production runs docker/Dockerfile.base, and drift between them ships as
# an ImportError at cold start.
echo "==> dependency layers…"
python3 "$REPO_ROOT/scripts/check_base_sync.py"

# Also stdlib-only. The specs and the tests are wired together by name, and
# nothing checked the wiring: a spec naming a renamed test claims coverage
# that is not there. Broken references fail; a scenario with no test only
# warns, because whether one is worth writing is a judgement.
echo "==> behaviour specs…"
python3 "$REPO_ROOT/scripts/check_specs.py"

# A comment between backslash-continued lines truncates the command and the
# truncated version often succeeds — the web service ran for an hour on a new
# image and the previous revision's environment. Twice now.
# Stdlib-only. Shared code must be a Bazel edge, not a path: the test
# selector reasons over the graph, and a consumer it cannot see is a consumer
# it will not re-test (python-conventions LP-9).
echo "==> import paths…"
python3 "$REPO_ROOT/scripts/check_import_paths.py"

# Code under test listed in a py_test's own srcs runs but is never
# instrumented, so it vanishes from CI's coverage summary. One bazel query.
echo "==> test srcs…"
python3 "$REPO_ROOT/scripts/check_test_srcs.py"

echo "==> workflow shell…"
python3 "$REPO_ROOT/scripts/check_workflow_shell.py"

# A credential typed literally into a URL. GitHub secret scanning only knows
# its partners' formats; a third party's embedded token (the JP app token
# sat in a public doc for five months) slips past it.
echo "==> url secrets…"
python3 "$REPO_ROOT/scripts/check_url_secrets.py"

echo "==> lint OK"
