#!/bin/bash
#
# Prepare an SD card for the AYN Thor 6 from the layout in this package.
#
#   ./sdcard.sh                 check the card and report what is on it
#   ./sdcard.sh prepare         create the folder tree on the card
#   ./sdcard.sh sync            copy BIOS/ and ROMs/ onto the card
#   ./sdcard.sh format          reformat the card (destructive, confirmed)
#
# The bare command is read-only. Anything that writes is a named subcommand,
# and the one that erases asks for the disk identifier before it does.
#
# This script moves files you already have. It does not obtain them, and
# nothing here will help you obtain them.

set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_BIOS="$PACKAGE_DIR/BIOS"
LOCAL_ROMS="$PACKAGE_DIR/ROMs"
DOCS_DIR="$PACKAGE_DIR/docs"
TEMPLATE_DIR="$PACKAGE_DIR/SD_TEMPLATE"

# exFAT because FAT32 cannot hold a file larger than 4 GB, and disc images
# reach that. macOS also offers MS-DOS (FAT32) by default when formatting a
# card, so this is worth checking rather than assuming.
WANTED_FS="exfat"

# Refusals and warnings go to stderr, and not for tidiness: `resolve_volume`
# is called inside `$( )`, so anything it writes to stdout is captured as the
# result instead of reaching the terminal. Sent there, a rejected card exits 1
# in silence and the user is told nothing.
red()  { printf '\033[31m%s\033[0m\n' "$*" >&2; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
info() { printf '%s\n' "$*" >&2; }
green(){ printf '\033[32m%s\033[0m\n' "$*"; }
bold() { printf '\033[1m%s\033[0m\n' "$*"; }

disclaimer() {
    cat <<'EOF'
────────────────────────────────────────────────────────────────────────
 This script copies files you supply. It does not download anything, and
 it will not help you find ROMs, disc images or BIOS dumps. Use dumps you
 made yourself from media you own.

 It writes to removable media and can erase a card. Back up anything on
 that card before running `format`.
────────────────────────────────────────────────────────────────────────
EOF
}

# --- the card ------------------------------------------------------------

# Every mounted volume that lives on a removable disk. Deliberately not
# "everything under /Volumes": that includes the boot disk.
list_candidates() {
    local vol parent
    for vol in /Volumes/*; do
        [ -d "$vol" ] || continue
        parent="$(whole_disk_of "$vol" 2>/dev/null)" || continue
        [ -n "$parent" ] || continue
        if is_removable "$parent"; then
            printf '%s\t%s\n' "$vol" "$parent"
        fi
    done
}

# The whole disk a volume sits on. `disk4s1` is a slice; `diskutil eraseDisk`
# takes `disk4`. Asking diskutil rather than trimming the string, because the
# safety checks below have to describe the object that actually gets erased.
whole_disk_of() {
    diskutil info -plist "$1" 2>/dev/null \
        | plutil -extract ParentWholeDisk raw - 2>/dev/null
}

plist_bool() {
    local value
    value="$(diskutil info -plist "$1" 2>/dev/null \
        | plutil -extract "$2" raw - 2>/dev/null)" || return 1
    [ "$value" = "true" ]
}

# The guard. Checked against the whole disk, never the mounted slice: those
# are different objects and only one of them is about to be erased.
is_removable() {
    local disk="$1"
    if plist_bool "$disk" Internal; then
        return 1
    fi
    plist_bool "$disk" Ejectable \
        || plist_bool "$disk" RemovableMediaOrExternalDevice
}

filesystem_of() {
    diskutil info -plist "$1" 2>/dev/null \
        | plutil -extract FilesystemType raw - 2>/dev/null \
        | tr '[:upper:]' '[:lower:]'
}

# Pick the card. One candidate is used; several make the user say which.
resolve_volume() {
    if [ -n "${SD_VOLUME:-}" ]; then
        [ -d "$SD_VOLUME" ] || { red "SD_VOLUME is not mounted: $SD_VOLUME"; exit 1; }
        # An override says *which* card, never *whether* it is one. Without
        # this, SD_VOLUME=/Volumes/Macintosh\ HD sails past the removable
        # filter and `sync` writes the collection onto the boot disk.
        local override_disk
        override_disk="$(whole_disk_of "$SD_VOLUME" || true)"
        if [ -z "$override_disk" ] || ! is_removable "$override_disk"; then
            red "REFUSING: $SD_VOLUME is not on a removable disk."
            info "  whole disk: ${override_disk:-unknown}"
            info "  This script only writes to removable media."
            exit 1
        fi
        printf '%s' "$SD_VOLUME"
        return
    fi
    local candidates count
    candidates="$(list_candidates)"
    count="$(printf '%s' "$candidates" | grep -c . || true)"
    if [ "$count" -eq 0 ]; then
        red "No removable volume mounted."
        info "Insert the card, or point at it: SD_VOLUME=/Volumes/NAME $0 ..."
        exit 1
    fi
    if [ "$count" -gt 1 ]; then
        red "More than one removable volume; say which:"
        printf '%s\n' "$candidates" | while IFS=$'\t' read -r v d; do
            info "   SD_VOLUME='$v' $0 ...   ($d)"
        done
        exit 1
    fi
    printf '%s' "$(printf '%s' "$candidates" | cut -f1)"
}

# --- the index guard -----------------------------------------------------

# The lesson from 2026-08-25: a `.gitignore` rule written on a feature branch
# is not in effect on the branch you are committing from, so `git check-ignore`
# answers about the rule rather than about the state. This asks the index
# instead — anything under BIOS/ or ROMs/ that git is tracking is the failure,
# and it is worth knowing before the card fills up rather than after.
assert_material_untracked() {
    local tracked
    tracked="$(git -C "$PACKAGE_DIR" ls-files -- BIOS ROMs 2>/dev/null \
        | grep -v '\.gitkeep$' || true)"
    if [ -n "$tracked" ]; then
        red "STOP — git is tracking emulation material:"
        printf '%s\n' "$tracked" | sed 's/^/   /'
        echo
        echo "This repository is public. Untrack them before going further:"
        echo "   git rm --cached <path>"
        exit 1
    fi
}

# --- subcommands ---------------------------------------------------------

cmd_check() {
    local vol disk fs
    vol="$(resolve_volume)"
    disk="$(whole_disk_of "$vol")"
    fs="$(filesystem_of "$vol")"

    bold "Card"
    echo "  volume:     $vol"
    echo "  whole disk: $disk"
    echo "  filesystem: ${fs:-unknown}"
    df -h "$vol" | tail -1 | awk '{print "  free:       " $4 " of " $2}'
    echo

    if [ "$fs" = "$WANTED_FS" ]; then
        green "  Filesystem is exFAT."
    else
        warn "  Filesystem is '${fs:-unknown}', not exFAT."
        echo "  FAT32 cannot hold a file larger than 4 GB, which some disc"
        echo "  images exceed. To reformat (this ERASES the card):"
        echo "      $0 format"
    fi
    echo
    cmd_status "$vol"
}

cmd_prepare() {
    local vol; vol="$(resolve_volume)"
    bold "Creating the folder tree on $vol"
    # The template is the shape; .gitkeep is scaffolding and does not belong
    # on the card. `find -type d` rather than copying, so an existing card
    # keeps whatever is already in those folders.
    (cd "$TEMPLATE_DIR" && find . -type d -mindepth 1) | while read -r dir; do
        mkdir -p "$vol/${dir#./}"
        echo "  $vol/${dir#./}"
    done
    green "Done."
}

cmd_sync() {
    assert_material_untracked
    local vol; vol="$(resolve_volume)"

    bold "Copying from this package to $vol"
    echo "  from: $LOCAL_BIOS"
    echo "        $LOCAL_ROMS"
    echo

    # exFAT carries no POSIX permissions or ownership, so rsync is told not to
    # try — without this it errors on every file. --modify-window=1 covers
    # FAT's two-second timestamp granularity, which otherwise makes every file
    # look changed on the next run.
    local flags=(-rh --progress --no-perms --no-owner --no-group
                 --modify-window=1 --exclude='.gitkeep' --exclude='.DS_Store')

    if [ -d "$LOCAL_BIOS" ]; then
        mkdir -p "$vol/BIOS"
        rsync "${flags[@]}" "$LOCAL_BIOS/" "$vol/BIOS/"
    fi
    if [ -d "$LOCAL_ROMS" ]; then
        mkdir -p "$vol/ROMs"
        rsync "${flags[@]}" "$LOCAL_ROMS/" "$vol/ROMs/"
    fi
    green "Copied."
    echo
    cmd_status "$vol"
}

cmd_status() {
    local vol="${1:-}"
    [ -n "$vol" ] || vol="$(resolve_volume)"
    local python; python="$(command -v python3)"
    bold "What is on the card"
    "$python" "$(dirname "${BASH_SOURCE[0]}")/inventory.py" \
        --docs "$DOCS_DIR" --roms "$vol/ROMs" --bios "$vol/BIOS"
}

cmd_format() {
    local vol disk size name
    vol="$(resolve_volume)"
    disk="$(whole_disk_of "$vol")"

    # Re-verify against the whole disk. `resolve_volume` already filtered on
    # this, but the thing about to be erased deserves its own check rather
    # than inheriting one made about a different object.
    if ! is_removable "$disk"; then
        red "REFUSING: $disk is not a removable disk."
        exit 1
    fi

    size="$(diskutil info -plist "$disk" | plutil -extract TotalSize raw - 2>/dev/null || echo 0)"
    name="$(diskutil info -plist "$disk" | plutil -extract MediaName raw - 2>/dev/null || echo '?')"

    echo
    red  "  THIS ERASES EVERYTHING ON THE DISK"
    echo "     disk:   $disk"
    echo "     media:  $name"
    echo "     size:   $(( size / 1000000000 )) GB"
    echo "     mounted as: $vol"
    echo
    echo "  Type the disk identifier ($disk) to confirm, anything else to stop."
    # The identifier, not the volume label: cards ship labelled UNTITLED, so a
    # label is neither unique nor a deliberate thing to type.
    printf "  > "
    read -r answer
    if [ "$answer" != "$disk" ]; then
        warn "Stopped. Nothing was changed."
        exit 1
    fi

    diskutil eraseDisk exFAT THOR6 "$disk"
    green "Formatted as exFAT, labelled THOR6."
    echo "Now: $0 prepare && $0 sync"
}

# --- entry ---------------------------------------------------------------

main() {
    case "${1:-check}" in
        check)   disclaimer; cmd_check ;;
        prepare) disclaimer; cmd_prepare ;;
        sync)    disclaimer; cmd_sync ;;
        status)  cmd_status ;;
        format)  disclaimer; cmd_format ;;
        *)
            sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 1
            ;;
    esac
}

main "$@"
