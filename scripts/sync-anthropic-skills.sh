#!/usr/bin/env bash
# scripts/sync-anthropic-skills.sh
#
# Vendors chosen skills from Anthropic's official skills repo into
# system/skills/<name>/, which scripts/install-system.sh installs into
# ~/.claude/skills/ for every project.
#
# Source: https://github.com/anthropics/skills (each skill Apache 2.0, its
# LICENSE.txt kept beside it). Cloned with git, not installed through a
# marketplace or npx. Review with `git diff --stat system/skills` before
# committing.
#
# Usage: scripts/sync-anthropic-skills.sh [skill ...]   (default: the list below)

set -euo pipefail

REPO_URL="https://github.com/anthropics/skills.git"
SKILLS=("$@")
if [ ${#SKILLS[@]} -eq 0 ]; then
  SKILLS=(frontend-design webapp-testing)
fi
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

git clone --depth 1 --quiet "$REPO_URL" "$TMP_DIR/repo"
commit="$(git -C "$TMP_DIR/repo" rev-parse HEAD)"

for skill in "${SKILLS[@]}"; do
  src="$TMP_DIR/repo/skills/$skill"
  if [ ! -f "$src/SKILL.md" ]; then
    echo "no skill named '$skill' in $REPO_URL" >&2
    exit 1
  fi
  dest="${ROOT}/system/skills/${skill}"
  mkdir -p "$dest"
  rsync -a --delete --exclude 'UPSTREAM' "$src/" "$dest/"
  printf '%s\n%s\n' "$REPO_URL" "$commit" > "$dest/UPSTREAM"
  echo "synced $skill at ${commit:0:12}"
done
git -C "$ROOT" status --short -- "${ROOT}/system/skills" | head -30
