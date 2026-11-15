#!/usr/bin/env bash
# scripts/sync-web-guidance.sh
#
# Vendors the modern-web-guidance skill from Google Chrome's official repo into
# system/skills/modern-web-guidance/, which scripts/install-system.sh installs
# into ~/.claude/skills/ for every project.
#
# Source: https://github.com/GoogleChrome/modern-web-guidance (Apache 2.0).
# Cloned with git rather than run through npx: the guides are read from disk.
# Review the result with `git diff --stat system/skills/modern-web-guidance`
# before committing.

set -euo pipefail

REPO_URL="https://github.com/GoogleChrome/modern-web-guidance.git"
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
DEST="${ROOT}/system/skills/modern-web-guidance"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

git clone --depth 1 --quiet "$REPO_URL" "$TMP_DIR/repo"
commit="$(git -C "$TMP_DIR/repo" rev-parse HEAD)"

mkdir -p "$DEST"
rsync -a --delete --exclude 'UPSTREAM' --exclude 'LICENSE' \
  "$TMP_DIR/repo/skills/modern-web-guidance/" "$DEST/"
cp "$TMP_DIR/repo/LICENSE" "$DEST/LICENSE"
printf '%s\n%s\n' "$REPO_URL" "$commit" > "$DEST/UPSTREAM"

echo "synced modern-web-guidance at ${commit:0:12}"
git -C "$ROOT" status --short -- "$DEST" | head -20
