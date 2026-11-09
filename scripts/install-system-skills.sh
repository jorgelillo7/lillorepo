#!/usr/bin/env bash
# scripts/install-system-skills.sh
#
# Installs the machine-level skills in system/skills/ into ~/.claude/skills/,
# so they load in every Claude Code session, whatever the project.
#
# They are copied, not symlinked: Claude Code does not reliably discover a
# symlinked skill directory. Edit them here, then run this again.
# Local output (reports/, the contacts config and exports) is never
# overwritten or deleted.

set -euo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
SRC="${ROOT}/system/skills"
DEST="${HOME}/.claude/skills"

mkdir -p "$DEST"
for skill in "$SRC"/*/; do
  name="$(basename "$skill")"
  rsync -a --delete \
    --exclude 'reports/' --exclude 'config.json' --exclude '*.vcf' \
    --exclude 'records.json' --exclude 'actions.json' --exclude 'decisions.json' \
    --exclude 'tests/' --exclude 'BUILD.bazel' --exclude '__pycache__/' \
    "$skill" "${DEST}/${name}/"
  echo "installed ${name}"
done
