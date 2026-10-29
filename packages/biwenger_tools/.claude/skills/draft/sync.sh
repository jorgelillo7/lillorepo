#!/usr/bin/env bash
# Copy the draft season folders to and from their private bucket.
#
#   bash packages/biwenger_tools/.claude/skills/draft/sync.sh push   # Mac → bucket
#   bash packages/biwenger_tools/.claude/skills/draft/sync.sh pull   # bucket → Mac
#
# Season folders are kept out of git (the repo is public). Nothing is ever
# deleted on either side: the bucket keeps versions, and a pull only adds or
# updates. The fetched payload cache stays local — it is reproducible.
set -euo pipefail

BUCKET="gs://biwenger-draft-private/seasons"
HERE="$(cd "$(dirname "$0")" && pwd)"

case "${1:-}" in
  push)
    for dir in "$HERE"/[0-9][0-9]-[0-9][0-9]; do
      [ -d "$dir" ] || continue
      season="$(basename "$dir")"
      gcloud storage rsync -r "$dir" "$BUCKET/$season" --exclude='.*\.cache/.*'
    done
    ;;
  pull)
    for season in $(gcloud storage ls "$BUCKET/" | sed -E 's#.*/([0-9]{2}-[0-9]{2})/$#\1#'); do
      mkdir -p "$HERE/$season"
      gcloud storage rsync -r "$BUCKET/$season" "$HERE/$season"
    done
    ;;
  *)
    echo "usage: $0 push|pull" >&2
    exit 2
    ;;
esac
