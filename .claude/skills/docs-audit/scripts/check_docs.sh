#!/bin/bash
# Documentation audit — mechanical checks over the repo's READMEs and docs.
# Bash 3 compatible (macOS default). Read-only: reports, never edits.
#
# Sections:
#   1. Inventory       — which docs are in scope
#   2. Broken links    — relative markdown links that don't resolve (the money check)
#   3. Facts to verify — hardcoded numbers / stale-marker phrases for the agent
#                        to cross-check against the source of truth
#
# Out of scope on purpose: externally-synced google-* skills, vendored trees.
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT"

# Newline-separated, deduped list of docs in scope.
doc_list() {
  {
    find . -iname 'README.md'
    find ./docs -iname '*.md' 2>/dev/null
    find ./packages -iname 'OPERATIONS.md' 2>/dev/null
    find ./packages -iname 'DESIGN.md' 2>/dev/null
    find ./packages -iname 'release-notes.md' 2>/dev/null
    for e in ./AGENTS.md ./CLAUDE.md ./STATUS.md ./INFRA.md ./PENDING.md; do
      [ -f "$e" ] && echo "$e"
    done
  } | grep -vE '/(node_modules|\.git|venv|\.pytest_cache)/|/\.claude/skills/' | sort -u
}

# Emit "file -> link" for every relative markdown link that doesn't resolve.
broken_links() {
  local f dir link target
  printf '%s\n' "$DOCS" | while IFS= read -r f; do
    [ -z "$f" ] && continue
    dir="$(dirname "$f")"
    grep -oE '\]\([^)]+\)' "$f" 2>/dev/null | sed -E 's/^\]\(//; s/\)$//' \
      | while IFS= read -r link; do
          target="${link%% *}"          # drop optional markdown "title"
          case "$target" in
            http*|'#'*|mailto:*|'') continue ;;
          esac
          target="${target%%#*}"        # strip in-page anchor
          [ -z "$target" ] && continue
          [ -e "$dir/$target" ] || echo "$f -> $link"
        done
  done
}

DOCS="$(doc_list)"
DOC_COUNT="$(printf '%s\n' "$DOCS" | grep -c . || true)"

echo "=========================================="
echo "  DOCS AUDIT — mechanical checks"
echo "=========================================="
echo

echo "== 1. Inventory ($DOC_COUNT docs in scope) =="
printf '%s\n' "$DOCS" | sed 's/^\.\//    /'
echo

echo "== 2. Broken relative links =="
BROKEN="$(broken_links)"
BROKEN_COUNT="$(printf '%s' "$BROKEN" | grep -c . || true)"
if [ "$BROKEN_COUNT" = "0" ]; then
  echo "    none ✅"
else
  printf '%s\n' "$BROKEN" | sed 's/^/    BROKEN: /'
fi
echo

echo "== 3. Facts to verify (cross-check against the source of truth) =="
echo "-- maturity score mentions (source of truth: STATUS.md) --"
printf '%s\n' "$DOCS" | while IFS= read -r f; do
  grep -nE '[0-9]+\.[0-9]+ ?/ ?10' "$f" 2>/dev/null | sed "s|^|    $f:|"
done
echo
echo "-- stale-marker phrases (a shipped feature shouldn't still say these) --"
printf '%s\n' "$DOCS" | while IFS= read -r f; do
  # Case-insensitive prose phrases:
  grep -inE '\b(coming soon|not yet (built|implemented)|under construction|to be (done|written)|work in progress)\b' \
    "$f" 2>/dev/null | sed "s|^|    $f:|"
  # Case-SENSITIVE code markers (avoids Spanish "todo", the filename todo.md):
  grep -nE '\b(TODO|FIXME|XXX|WIP)\b' "$f" 2>/dev/null | sed "s|^|    $f:|"
done
echo
echo "-- packages under /packages not mentioned in root README.md --"
MISS=0
for p in packages/*/; do
  [ -d "$p" ] || continue
  name="$(basename "$p")"
  case "$name" in __*|.*) continue ;; esac   # skip __pycache__ and dotdirs
  if ! grep -q "$name" README.md 2>/dev/null; then
    echo "    ⚠ '$name' not referenced in root README.md"
    MISS=1
  fi
done
[ "$MISS" = "0" ] && echo "    all packages referenced ✅"
echo

echo "=========================================="
echo "  SUMMARY: $DOC_COUNT docs · $BROKEN_COUNT broken link(s)"
echo "  Section 3 lists candidates, not errors — the skill judges them."
echo "=========================================="
