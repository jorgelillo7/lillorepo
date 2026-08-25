#!/bin/bash
# Run black --check and flake8 hermetically with the same Python (3.13) CI uses.
#
# Why: black 26.3.1 produces slightly different output across Python versions
# (3.12 on the maintainer's Mac vs 3.13 on CI), which caused multiple CI
# fixup commits. Running both linters through Bazel's hermetic toolchain
# removes the drift.
#
# Usage: bash scripts/lint.sh           # check core/ and packages/
#        bash scripts/lint.sh --fix     # format with black (in place) instead
#
# First invocation is slow (Bazel resolves the lint targets); later ones use
# the cache.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TARGETS=("core/" "packages/")

if [[ "${1:-}" == "--fix" ]]; then
    echo "==> black (writing changes)…"
    bazel run --ui_event_filters=-info,-stdout,-stderr //tools/lint:black -- \
        "${TARGETS[@]/#/$REPO_ROOT/}"
    echo "==> flake8…"
    bazel run --ui_event_filters=-info,-stdout,-stderr //tools/lint:flake8 -- \
        "${TARGETS[@]/#/$REPO_ROOT/}"
    exit 0
fi

echo "==> black --check…"
bazel run --ui_event_filters=-info,-stdout,-stderr //tools/lint:black -- \
    --check "${TARGETS[@]/#/$REPO_ROOT/}"

echo "==> flake8…"
bazel run --ui_event_filters=-info,-stdout,-stderr //tools/lint:flake8 -- \
    "${TARGETS[@]/#/$REPO_ROOT/}"

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

# The emulation package's README tells anyone arriving at this public
# repository that it holds no game data, and invites them to verify it. This
# runs that verification, so the claim cannot quietly stop being true.
echo "==> emulation package…"
python3 "$REPO_ROOT/scripts/check_no_game_data.py"

echo "==> lint OK"
