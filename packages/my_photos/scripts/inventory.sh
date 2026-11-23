#!/usr/bin/env bash
# inventory.sh — measure where the user's photos live today.
#
# Reads-only. Run before any cleanup decision to confirm the numbers we are
# planning against.
#
# Reports for the Mac:
#   - Apple Photos library size (the local .photoslibrary bundle)
#   - External drives currently mounted (any /Volumes/* that is not the
#     system disk), with their free/used space and the count of folders
#     matching the YYYY-MM-DD convention.
#
# Cloud services do not expose sizes from the Mac, so iCloud and Google
# Photos are shown as static reference values. Update the constants below
# when those numbers change.

set -euo pipefail

# --- Static reference values -----------------------------------------------
ICLOUD_GB="26.89"
ICLOUD_PHOTOS="3933"
ICLOUD_VIDEOS="598"
ICLOUD_PLAN_GB="200"
GOOGLE_PHOTOS_GB="6.21"
GOOGLE_TOTAL_GB="9.91"
GOOGLE_PLAN_TB="5"

# The library folder is localised (Imágenes or Pictures); both are checked.
LIBRARY_CANDIDATES=(
    "${HOME}/Imágenes/Photos Library.photoslibrary"
    "${HOME}/Pictures/Photos Library.photoslibrary"
)
LIBRARY=""
for candidate in "${LIBRARY_CANDIDATES[@]}"; do
    if [[ -d "$candidate" ]]; then
        LIBRARY="$candidate"
        break
    fi
done

# --- Helpers ---------------------------------------------------------------
section() {
    echo
    echo "─── $1 ───────────────────────────────────────────────────"
}

pct() {
    awk "BEGIN{printf \"%.0f\", ($1/$2)*100}"
}

# --- Apple Photos library --------------------------------------------------
section "📷 Apple Photos library (local)"
if [[ -z "$LIBRARY" ]]; then
    echo "⚠️  Not found in any of:"
    for candidate in "${LIBRARY_CANDIDATES[@]}"; do
        echo "     · $candidate"
    done
    echo "   If your library is elsewhere, add the path to LIBRARY_CANDIDATES."
else
    echo "Path: $LIBRARY"
    # `du -sh` on the library fails with "Operation not permitted" unless
    # the terminal has Full Disk Access. We detect that and tell the user.
    if size=$(du -sh "$LIBRARY" 2>/dev/null); then
        echo "Size on disk: $(echo "$size" | cut -f1)  (note: 'Optimize"
        echo "                       storage' keeps only previews + recent"
        echo "                       originals; full set lives in iCloud)"
    else
        echo "Size on disk: ⚠️  not readable from this terminal"
        echo "   macOS sandboxes Photos Library by default. To measure it from a"
        echo "   shell, grant Full Disk Access:"
        echo "     System Settings > Privacy & Security > Full Disk Access > add Terminal/iTerm"
        echo "   Or just rely on the iCloud value above as a proxy (the local"
        echo "   library is mostly previews anyway in Optimize Storage mode)."
    fi
fi

# --- iCloud (reference) ----------------------------------------------------
section "☁️  iCloud Photos (reference)"
printf "Plan: %5s GB    Used: %s GB (%s photos + %s videos)    Usage: %s%%\n" \
    "$ICLOUD_PLAN_GB" "$ICLOUD_GB" "$ICLOUD_PHOTOS" "$ICLOUD_VIDEOS" \
    "$(pct "$ICLOUD_GB" "$ICLOUD_PLAN_GB")"
echo "(no public API from the Mac — update the constants at the top when"
echo " you re-check Configuración > Apple ID > iCloud > Fotos)"

# --- Google One (reference) ------------------------------------------------
section "🔵 Google One (reference)"
printf "Plan: %s TB    Used: %s GB total (%s GB in Google Photos)\n" \
    "$GOOGLE_PLAN_TB" "$GOOGLE_TOTAL_GB" "$GOOGLE_PHOTOS_GB"
echo "(kept for Gemini and YouTube; the 'familia' account draws from this pool)"

# --- External drives -------------------------------------------------------
section "💾 External drives currently mounted"
if [[ ! -d /Volumes ]]; then
    echo "⚠️  /Volumes does not exist (not running on macOS?)"
elif [[ "$(ls /Volumes 2>/dev/null | wc -l | tr -d ' ')" == "0" ]]; then
    echo "⚠️  Nothing mounted under /Volumes"
else
    found_external=0
    for vol in /Volumes/*; do
        [[ -d "$vol" ]] || continue
        # Skip the system disk by name
        case "$(basename "$vol")" in
            "Macintosh HD"|"Macintosh HD - Data"|".timemachine"|com.apple.*)
                continue
                ;;
        esac
        found_external=1
        name=$(basename "$vol")
        used=$(df -h "$vol" 2>/dev/null | tail -1 | awk '{print $3}')
        total=$(df -h "$vol" 2>/dev/null | tail -1 | awk '{print $2}')
        avail=$(df -h "$vol" 2>/dev/null | tail -1 | awk '{print $4}')
        # Count event folders matching YYYY-MM-DD (depth ≤ 3)
        events=$(find "$vol" -maxdepth 3 -type d -name "20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]*" 2>/dev/null | wc -l | tr -d ' ')
        printf "%-30s  used %5s / %5s  (%5s free)  · %d event folders\n" \
            "$name" "$used" "$total" "$avail" "$events"
    done
    if [[ "$found_external" == "0" ]]; then
        echo "⚠️  No external drives detected (only system volumes)"
        echo "   Plug the old drive (historic photos) and the new 5 TB drive,"
        echo "   then re-run for a complete inventory."
    fi
fi

# --- Hint -----------------------------------------------------------------
section "🎯 Next"
cat <<'EOF'
Compare these numbers with packages/my_photos/README.md (Capacity):
  - iCloud usage against 200 GB -> when to move to 2 TB or trim
  - external drives -> the old disk and the 5 TB copy, with their event folders

If anything looks unexpected, adjust the plan before writing any code that
touches the photos.
EOF
