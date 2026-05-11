#!/usr/bin/env bash
set -euo pipefail

RPI_BASE="$HOME/.claude/rpi"

dirs=(
  "$RPI_BASE/researchs"
  "$RPI_BASE/plans"
  "$RPI_BASE/todos"
)

for dir in "${dirs[@]}"; do
  if [ ! -d "$dir" ]; then
    mkdir -p "$dir"
    echo "Created: $dir"
  fi
done

echo "RPI directories verified at $RPI_BASE"
