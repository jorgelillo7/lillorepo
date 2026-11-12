#!/usr/bin/env bash
# scripts/install-system.sh
#
# Installs the personal skills in system/skills/ into ~/.claude/skills/, the
# personal rules in system/rules/ into ~/.claude/rules/ and the subagent roles
# in system/agents/ into ~/.claude/agents/, so they load in every Claude Code
# session, whatever the project.
#
# They are copied, not symlinked: Claude Code does not reliably discover a
# symlinked skill directory. Edit them here, then run this again. Skills'
# local output (reports/, the contacts config and exports) is never
# overwritten or deleted, and a rule or role written by hand in ~/.claude/rules/
# or ~/.claude/agents/ is left alone.

set -euo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
SRC="${ROOT}/system/skills"
DEST="${HOME}/.claude/skills"
RULES_SRC="${ROOT}/system/rules"
RULES_DEST="${HOME}/.claude/rules"
AGENTS_SRC="${ROOT}/system/agents"
AGENTS_DEST="${HOME}/.claude/agents"

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

mkdir -p "$RULES_DEST"
for rule in "$RULES_SRC"/*.md; do
  cp "$rule" "${RULES_DEST}/"
  echo "installed rule $(basename "$rule")"
done

mkdir -p "$AGENTS_DEST"
for role in "$AGENTS_SRC"/*.md; do
  cp "$role" "${AGENTS_DEST}/"
  echo "installed agent $(basename "$role" .md)"
done
