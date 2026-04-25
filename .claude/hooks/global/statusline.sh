#!/bin/bash
# Claude Code Status Line — global script (see .claude/hooks/global/README.md)
# Shows model, context usage percentage, and total cost

input=$(cat)

MODEL=$(echo "$input" | jq -r '.model.display_name // "unknown"')
CTX=$(echo "$input" | jq -r '.context_window.used_percentage // 0' | cut -d. -f1)
COST=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')

# Format the cost with LC_NUMERIC=C so macOS uses a decimal point.
COST_FORMATTED=$(LC_NUMERIC=C awk -v cost="$COST" 'BEGIN {printf "%.4f", cost}')

echo "[$MODEL] 📊 ${CTX}% | 💰 \$${COST_FORMATTED}"
