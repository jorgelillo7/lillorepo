#!/usr/bin/env bash
# scripts/sync-google-skills.sh
#
# Selectively syncs Agent Skills from the official google/skills repo into
# this project's .claude/skills/ directory.
#
# Source: https://github.com/google/skills (Apache 2.0, official Google org)
# Avoids `npx skills add` to stay clear of third-party installers — the only
# external trust is git + github.com/google/skills.

set -euo pipefail

REPO_URL="https://github.com/google/skills.git"
PREFIX="google-"

# Build the local skill directory name from an upstream skill name. Some
# upstream skills already start with `google-` (e.g. `google-cloud-waf-security`)
# — don't double the prefix in that case.
local_name() {
  local upstream="$1"
  if [[ "$upstream" == ${PREFIX}* ]]; then
    printf '%s\n' "$upstream"
  else
    printf '%s\n' "${PREFIX}${upstream}"
  fi
}

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$PROJECT_ROOT" ]]; then
  echo "error: not inside a git repository." >&2
  exit 1
fi
DEST_DIR="${PROJECT_ROOT}/.claude/skills"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [args]

Syncs Google Cloud skills from ${REPO_URL}
into ${DEST_DIR}/${PREFIX}* (project-level skills).

Commands:
  list                  Show skills available upstream
  add <skill> [...]     Install or update one or more skills by name
  sync                  Check every installed Google skill for upstream changes
  remove <skill> [...]  Delete one or more installed Google skills

Every overwrite is confirmed interactively. Diffs are shown before applying.
EOF
}

clone_upstream() {
  echo "Cloning google/skills (shallow)…" >&2
  git clone --depth 1 --quiet "$REPO_URL" "$TMP_DIR/repo"
}

# List skills present upstream (one per line), portable across BSD/GNU find.
list_upstream_skills() {
  local d
  for d in "$TMP_DIR/repo/skills"/*/*/; do
    [[ -d "$d" ]] || continue
    basename "$d"
  done | sort
}

# Resolve the upstream directory for a skill name. Echoes the absolute path
# or returns 1 if not found.
find_upstream_skill() {
  local name="$1" d
  for d in "$TMP_DIR/repo/skills"/*/"$name"/; do
    [[ -d "$d" ]] || continue
    printf '%s\n' "${d%/}"
    return 0
  done
  return 1
}

# List installed skills (basenames), one per line. Returns the on-disk name —
# either `google-<x>` or already-prefixed `google-cloud-<x>`.
list_installed_skills() {
  local d
  for d in "$DEST_DIR/${PREFIX}"*/; do
    [[ -d "$d" ]] || continue
    basename "$d"
  done | sort
}

# Show which files differ between local and upstream copies of a skill.
show_diff_summary() {
  local local_dir="$1"
  local upstream_dir="$2"
  diff -rq "$local_dir" "$upstream_dir" 2>/dev/null \
    | sed -e "s|$TMP_DIR/repo|<upstream>|g" -e "s|$DEST_DIR|<local>|g" \
    | sed 's/^/    /'
}

confirm() {
  local prompt="$1" answer
  read -r -p "$prompt [y/N] " answer
  [[ "$answer" =~ ^[Yy] ]]
}

# Write a license notice once, alongside the synced skills. Required because
# google/skills is Apache 2.0 and lillorepo is public.
ensure_license_notice() {
  local notice="$DEST_DIR/GOOGLE-SKILLS-LICENSE.md"
  [[ -f "$notice" ]] && return
  mkdir -p "$DEST_DIR"
  cat > "$notice" <<'EOF'
# Google Skills — License Notice

The `google-*` skills in this directory are sourced from the official Google
Agent Skills repository:

  https://github.com/google/skills

Licensed under the Apache License 2.0:

  https://github.com/google/skills/blob/main/LICENSE

They are synced via `scripts/sync-google-skills.sh`. Run that script to check
for upstream changes or to install/remove skills.
EOF
}

cmd_list() {
  clone_upstream
  echo ""
  list_upstream_skills
}

cmd_add() {
  if [[ $# -eq 0 ]]; then
    echo "error: 'add' requires at least one skill name." >&2
    echo "       Run '$(basename "$0") list' to see what's available." >&2
    exit 1
  fi
  clone_upstream
  ensure_license_notice
  for name in "$@"; do
    local src dest dirname
    src="$(find_upstream_skill "$name" || true)"
    if [[ -z "$src" ]]; then
      echo "⚠ ${name}: not found upstream"
      continue
    fi
    dirname="$(local_name "$name")"
    dest="$DEST_DIR/${dirname}"
    if [[ -d "$dest" ]]; then
      if diff -rq "$src" "$dest" >/dev/null 2>&1; then
        echo "✓ ${dirname}: already up to date"
        continue
      fi
      echo ""
      echo "🔄 ${dirname} differs from upstream:"
      show_diff_summary "$dest" "$src"
      if ! confirm "Overwrite ${dirname}?"; then
        echo "  skipped."
        continue
      fi
      rm -rf "$dest"
    fi
    cp -R "$src" "$dest"
    echo "✓ ${dirname}: installed"
  done
}

cmd_sync() {
  clone_upstream
  if [[ ! -d "$DEST_DIR" ]]; then
    echo "No skills directory at $DEST_DIR — nothing to sync."
    return
  fi
  local installed
  installed="$(list_installed_skills)"
  if [[ -z "$installed" ]]; then
    echo "No Google skills installed (prefix '${PREFIX}')."
    echo "Use: $(basename "$0") add <skill>"
    return
  fi
  echo ""
  for dirname in $installed; do
    local src dest upstream_name
    # The on-disk dir is `google-<x>`; upstream name might be the same
    # (e.g. `google-cloud-waf-security`) or stripped (`cloud-run-basics`).
    upstream_name="${dirname#${PREFIX}}"
    src="$(find_upstream_skill "$upstream_name" || true)"
    if [[ -z "$src" ]]; then
      # Try with the prefix intact in case the upstream name is `google-...`
      src="$(find_upstream_skill "$dirname" || true)"
    fi
    dest="$DEST_DIR/${dirname}"
    if [[ -z "$src" ]]; then
      echo "⚠ ${dirname}: no longer in upstream (kept locally)"
      continue
    fi
    if diff -rq "$src" "$dest" >/dev/null 2>&1; then
      echo "✓ ${dirname}: up to date"
      continue
    fi
    echo ""
    echo "🔄 ${dirname} has upstream changes:"
    show_diff_summary "$dest" "$src"
    if ! confirm "Update ${dirname}?"; then
      echo "  kept current version."
      continue
    fi
    rm -rf "$dest"
    cp -R "$src" "$dest"
    echo "  ✓ updated."
  done
}

cmd_remove() {
  if [[ $# -eq 0 ]]; then
    echo "error: 'remove' requires at least one skill name." >&2
    exit 1
  fi
  for name in "$@"; do
    local dirname dest
    dirname="$(local_name "$name")"
    dest="$DEST_DIR/${dirname}"
    if [[ ! -d "$dest" ]]; then
      echo "  ${dirname}: not installed"
      continue
    fi
    rm -rf "$dest"
    echo "✓ removed ${dirname}"
  done
}

case "${1:-}" in
  list) shift; cmd_list "$@" ;;
  add) shift; cmd_add "$@" ;;
  sync) shift; cmd_sync "$@" ;;
  remove) shift; cmd_remove "$@" ;;
  -h|--help|help) usage ;;
  "") usage; exit 1 ;;
  *) echo "error: unknown command '$1'" >&2; usage; exit 1 ;;
esac
