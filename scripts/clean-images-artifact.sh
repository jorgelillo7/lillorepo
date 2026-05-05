#!/bin/bash
# Garbage-collect Artifact Registry to stay inside the free tier.
#
# Two strategies:
#   - SIMPLE_IMAGES (web, scraper_job, teams_analyzer): single-arch images
#     pushed via rules_oci's oci_push. Keep only the most recent digest, drop
#     the rest.
#   - MULTI_ARCH_IMAGES (python-base): multi-arch images pushed via docker
#     buildx. The tagged "latest" is a manifest list referencing per-arch
#     children that are themselves untagged — never delete recent untagged
#     digests, only the orphans older than $UNTAGGED_MIN_AGE_HOURS.
#
# Set DRY_RUN=1 to preview without deleting.

set -euo pipefail

REPO="europe-southwest1-docker.pkg.dev/biwenger-tools/biwenger-docker"
SIMPLE_IMAGES=("web" "scraper_job" "teams_analyzer" "telegram_bot")
MULTI_ARCH_IMAGES=("python-base")
UNTAGGED_MIN_AGE_HOURS="${UNTAGGED_MIN_AGE_HOURS:-24}"
DRY_RUN="${DRY_RUN:-0}"

run() {
    if [ "$DRY_RUN" = "1" ]; then
        echo "[DRY_RUN] $*"
    else
        "$@"
    fi
}

# --- SIMPLE: keep only the newest digest per image ---
echo "--- Simple images (keep newest only) ---"
for IMAGE in "${SIMPLE_IMAGES[@]}"; do
    echo "[INFO] Cleaning $IMAGE"

    # Note: the resource field is `version` (sha256:...), not `digest`. The
    # `DIGEST` column in `gcloud artifacts docker images list` output is
    # cosmetic — using --format="get(digest)" returns empty.
    DIGESTS_TO_DELETE=$(gcloud artifacts docker images list "$REPO/$IMAGE" \
        --sort-by=~CREATE_TIME \
        --format="value(version)" \
        --quiet 2>/dev/null | tail -n +2 || true)

    if [ -z "$DIGESTS_TO_DELETE" ]; then
        echo "[OK] Nothing to delete for $IMAGE."
        continue
    fi

    while IFS= read -r DIGEST; do
        [ -z "$DIGEST" ] && continue
        echo "[ACTION] Deleting old digest: $IMAGE@$DIGEST"
        run gcloud artifacts docker images delete "$REPO/$IMAGE@$DIGEST" \
            --delete-tags --quiet
    done <<< "$DIGESTS_TO_DELETE"
    echo "[OK] $IMAGE cleaned."
done

echo ""

# --- MULTI-ARCH: drop only orphan untagged digests older than $UNTAGGED_MIN_AGE_HOURS ---
echo "--- Multi-arch images (drop untagged orphans older than ${UNTAGGED_MIN_AGE_HOURS}h) ---"

# Compute the cutoff timestamp in RFC3339 (works on both BSD and GNU date).
if date -v-1H +%s >/dev/null 2>&1; then
    CUTOFF=$(date -u -v-"${UNTAGGED_MIN_AGE_HOURS}"H +%Y-%m-%dT%H:%M:%SZ)
else
    CUTOFF=$(date -u -d "-${UNTAGGED_MIN_AGE_HOURS} hours" +%Y-%m-%dT%H:%M:%SZ)
fi
echo "[INFO] Cutoff: $CUTOFF"

for IMAGE in "${MULTI_ARCH_IMAGES[@]}"; do
    echo "[INFO] Cleaning $IMAGE"

    # Two passes: a manifest list cannot be deleted before its children, but
    # children also cannot be deleted while a parent references them. Hit it
    # twice and tolerate "referenced by parent" errors on the first pass —
    # the second pass mops up whatever was blocked.
    for PASS in 1 2; do
        UNTAGGED_DIGESTS=$(gcloud artifacts docker images list "$REPO/$IMAGE" \
            --filter="-tags:* AND createTime<\"$CUTOFF\"" \
            --format="value(version)" \
            --quiet 2>/dev/null || true)

        if [ -z "$UNTAGGED_DIGESTS" ]; then
            [ "$PASS" = "1" ] && echo "[OK] No old untagged digests for $IMAGE."
            break
        fi

        while IFS= read -r DIGEST; do
            [ -z "$DIGEST" ] && continue
            echo "[ACTION] Deleting orphan (pass $PASS): $IMAGE@$DIGEST"
            if [ "$DRY_RUN" = "1" ]; then
                echo "[DRY_RUN] gcloud artifacts docker images delete $REPO/$IMAGE@$DIGEST --quiet"
            else
                gcloud artifacts docker images delete \
                    "$REPO/$IMAGE@$DIGEST" --quiet 2>&1 \
                    | grep -vE 'manifest has referenced parents|failed precondition' \
                    || true
            fi
        done <<< "$UNTAGGED_DIGESTS"
    done
    echo "[OK] $IMAGE cleaned."
done

echo ""
echo "--- Done ---"
