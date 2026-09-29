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
for f in core/requirements.txt packages/*/*/requirements.txt; do
    [ -f "$f" ] || continue
    dim "  $f"
    grep -vE '^[[:space:]]*(#|$)' "$f" | sed 's/^/    /'
done
echo

bold "Pinned versions of critical libs (requirements_lock.txt)"
CRITICAL_LIBS=(
    flask gunicorn requests beautifulsoup4 unidecode python-dotenv
    google-api-python-client google-auth google-cloud-firestore python-dateutil
    python-json-logger matplotlib pillow cryptography flake8 black pytest
)
for pkg in "${CRITICAL_LIBS[@]}"; do
    line=$(grep -E "^${pkg}==" requirements_lock.txt 2>/dev/null | head -1)
    [ -n "$line" ] && printf "  %s\n" "$line"
done
echo

# Lint tooling (flake8/black) is covered by CRITICAL_LIBS above: CI runs it
# hermetically through Bazel from the same lockfile, nothing extra is pinned
# in the workflows.

# The tooling that regenerates the lock lives outside it (venv/), so nothing
# above would notice it broken. It once was: a pip-tools pin crashed on the
# venv's pip, wrote nothing, and a silenced run passed for a reproduced lock.
# So this section *runs* pip-compile (dry run) instead of trusting a version.
bold "Lock tooling (${VENV:=venv}/)"
if [ ! -x "$VENV/bin/python" ]; then
    printf "  %s missing — create it as docs/operations.md says\n" "$VENV"
else
    VENV_PY=$("$VENV/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
    LOCK_PY=$(sed -n 's/.*pip-compile with Python \([0-9.]*\).*/\1/p' requirements_lock.txt | head -1)
    PT_VER=$("$VENV/bin/pip-compile" --version 2>/dev/null | awk '{print $NF}')
    PT_DOC=$(grep -oE 'pip-tools==[0-9.]+' docs/operations.md | head -1 | cut -d= -f3)
    printf "  venv Python: %s (lock targets %s)%s\n" "$VENV_PY" "${LOCK_PY:-?}" \
        "$([ "$VENV_PY" = "$LOCK_PY" ] || echo '  ⚠️  MISMATCH')"
    printf "  pip-tools:   %s (docs/operations.md pins %s)%s\n" "${PT_VER:-not installed}" \
        "${PT_DOC:-?}" "$([ "$PT_VER" = "$PT_DOC" ] || echo '  ⚠️  MISMATCH')"
    DRY_LOG=$(mktemp)
    if "$VENV/bin/pip-compile" --dry-run --quiet requirements.in >/dev/null 2>"$DRY_LOG"; then
        printf "  pip-compile --dry-run: ✅ resolves\n"
    else
        printf "  pip-compile --dry-run: 🔴 FAILS — %s\n" "$(grep -vE 'strip-extras|^\s*$' "$DRY_LOG" | tail -1 | cut -c1-110)"
    fi
    rm -f "$DRY_LOG"
fi
echo
