#!/usr/bin/env bash
# Print a concise snapshot of the project's critical pinned versions.
# Sources of truth: .bazelversion, MODULE.bazel, .github/workflows/*.yml,
# requirements_lock.txt and each module's requirements.txt.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
dim()  { printf "\033[2m%s\033[0m\n" "$1"; }

bold "Build / runtime"
printf "  Bazel:    %s\n" "$(cat .bazelversion 2>/dev/null || echo '?')"
PYTHON_VERSION=$(grep -oE 'python_version = "[^"]+"' MODULE.bazel | head -1 \
    | sed 's/.*"\([^"]*\)".*/\1/')
printf "  Python:   %s\n" "${PYTHON_VERSION:-?}"
echo

bold "Bazel modules (MODULE.bazel)"
grep -E '^bazel_dep\(' MODULE.bazel \
    | sed -E 's/.*name = "([^"]+)", version = "([^"]+)".*/  \1: \2/'
echo

bold "GitHub Actions"
grep -hE '^[[:space:]]*-?[[:space:]]*uses:' .github/workflows/*.yml \
    | sed -E 's/^[[:space:]]*-?[[:space:]]*uses:[[:space:]]*/  /' \
    | sort -u
echo

bold "Direct Python deps (per-module requirements.txt)"
for f in core/requirements.txt packages/biwenger_tools/*/requirements.txt; do
    [ -f "$f" ] || continue
    dim "  $f"
    grep -vE '^[[:space:]]*(#|$)' "$f" | sed 's/^/    /'
done
echo

bold "Pinned versions of critical libs (requirements_lock.txt)"
CRITICAL_LIBS=(
    flask gunicorn requests beautifulsoup4 unidecode python-dotenv
    google-api-python-client google-auth python-dateutil python-json-logger
    flake8 black pytest
)
for pkg in "${CRITICAL_LIBS[@]}"; do
    line=$(grep -E "^${pkg}==" requirements_lock.txt 2>/dev/null | head -1)
    [ -n "$line" ] && printf "  %s\n" "$line"
done
echo

bold "Tooling pinned in CI"
grep -hE 'flake8==|black==' .github/workflows/deploy.yml \
    | sed -E 's/^[[:space:]]*/  /' | sort -u
