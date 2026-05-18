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

echo "==> lint OK"
