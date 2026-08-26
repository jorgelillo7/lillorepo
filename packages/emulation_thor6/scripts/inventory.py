"""What is on the card, measured against what the guide lists.

Pure: paths in, a report out, nothing written and no disk touched. The
`diskutil` half of this lives in `sdcard.sh`, which cannot be unit-tested and
does not pretend to be; everything worth a test is here.

The two halves of the answer are reported differently on purpose:

- **BIOS filenames are standardised**, so "present" and "absent" are facts and
  are stated as such.
- **Game filenames are not.** A dump can be named anything, so matching a
  checklist title against a filename is a guess. An unmatched title is
  reported as *not obviously present*, never as missing — telling someone to
  go and find a game they already own, under a name this script did not
  recognise, is worse than saying nothing.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# BIOS files each system needs. Only systems that actually require one appear;
# the guide's others boot without.
#
# `patterns` are fnmatch-style, matched case-insensitively, because a console
# BIOS is dumped under a dozen names that share a prefix. `size` is what
# separates the two PlayStations: both are dumped as `scphNNNN.bin` and no
# filename pattern tells them apart reliably, but a PS1 image is 512 KB and a
# PS2 image 4 MB. Matching on the name alone reported "PS2 satisfied" off a
# PS1 dump — a false positive on the one system that will not boot without
# the real thing.
#
# `size` is None where the name is already unambiguous.
BIOS_REQUIREMENTS = {
    "PlayStation 1 (DuckStation)": {
        "patterns": ["scph*.bin", "ps-*.bin", "psxonpsp*.bin"],
        "size": 512 * 1024,
    },
    "PlayStation 2 (NetherSX2)": {
        "patterns": ["scph*.bin", "ps2-*.bin"],
        "size": 4 * 1024 * 1024,
    },
    "Dreamcast (Flycast)": {
        "patterns": ["dc_boot.bin", "dc_flash.bin"],
        "size": None,
    },
    "Neo Geo (FBNeo, Metal Slug)": {
        "patterns": ["neogeo.zip"],
        "size": None,
    },
}

# How far a dump may sit from its nominal size and still count. Dumps carry
# small header or padding differences between tools; the two PlayStation sizes
# are three orders of magnitude apart, so this needs no precision to separate
# them.
_SIZE_TOLERANCE = 0.10

# Extensions that are game images rather than the debris a card accumulates.
# Archives count: arcade sets are zips and must stay that way.
_ROM_SUFFIXES = {
    ".zip",
    ".7z",
    ".chd",
    ".cue",
    ".bin",
    ".iso",
    ".img",
    ".gba",
    ".gb",
    ".gbc",
    ".nds",
    ".3ds",
    ".cia",
    ".gdi",
    ".cdi",
    ".gcm",
    ".rvz",
    ".wbfs",
    ".md",
    ".gen",
    ".sms",
    ".smd",
    ".pbp",
    ".cso",
    ".m3u",
}

# Files every card ends up with that are not games.
_IGNORED_NAMES = {".gitkeep", ".ds_store"}


def _normalise(text: str) -> set:
    """A title reduced to comparable words.

    Accents, punctuation and case all vary between a checklist entry and
    whatever the file ended up called, and none of them carry meaning here.
    Roman numerals are left alone: "Golden Axe II" and "Golden Axe" are
    different games and collapsing them would be worse than not matching.
    """
    stripped = "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )
    words = re.split(r"[^a-z0-9]+", stripped)
    return {w for w in words if w and len(w) > 1}


def parse_guide(docs_dir: Path) -> list:
    """Read the per-system documents into `[{system, folder, titles}]`.

    The documents are the source of truth for both the checklist and the
    folder each system's files belong in — they already state both, and a
    second copy here would be one to keep in sync.
    """
    systems = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.+)$", text, re.M)
        folder_match = re.search(r"\*\*Games go in:\*\*\s*`([^`]+)`", text)
        if not (title_match and folder_match):
            continue
        # "SD_TEMPLATE/ROMs/psx/" -> "psx". A doc covering two folders (the
        # GameCube/Wii one) names the first; its second is picked up by the
        # `and` clause the document writes.
        folders = re.findall(r"ROMs/([a-z0-9_]+)/", folder_match.group(1))
        titles = re.findall(r"^-\s*\[\s*\]\s*(.+?)\s*$", text, re.M)
        systems.append(
            {
                "system": title_match.group(1).strip(),
                "doc": path.name,
                "folders": folders,
                # "Resident Evil — see notes" is one game with a footnote, not
                # a title containing a dash.
                "titles": [re.split(r"\s+—\s+", t)[0].strip() for t in titles],
            }
        )
    return systems


def scan_roms(roms_root: Path) -> dict:
    """`{folder: [filenames]}` for each system directory that exists."""
    found = {}
    if not roms_root.is_dir():
        return found
    for child in sorted(roms_root.iterdir()):
        if not child.is_dir():
            continue
        found[child.name] = sorted(
            f.name
            for f in child.rglob("*")
            if f.is_file()
            and f.name.lower() not in _IGNORED_NAMES
            and f.suffix.lower() in _ROM_SUFFIXES
        )
    return found


def match_titles(titles: list, filenames: list) -> tuple:
    """Split a checklist into `(likely_present, not_obviously_present)`.

    A title counts as present when every significant word in it appears in
    some filename. That is deliberately strict in one direction: it will miss
    a file named in Japanese or abbreviated past recognition, and those land
    in the second list — which is why that list is not called "missing".
    """
    normalised_files = [_normalise(name) for name in filenames]
    present, unclear = [], []
    for title in titles:
        words = _normalise(title)
        if words and any(words <= file_words for file_words in normalised_files):
            present.append(title)
        else:
            unclear.append(title)
    return present, unclear


def check_bios(bios_dir: Path) -> dict:
    """`{label: {"required": [...], "found": [...], "satisfied": bool}}`.

    Unlike the games this is close to exact — the filenames are fixed by the
    emulators that read them — with size used where the name is not enough.
    See `BIOS_REQUIREMENTS`.
    """
    from fnmatch import fnmatch

    files = (
        [(f.name, f.stat().st_size) for f in bios_dir.iterdir() if f.is_file()]
        if bios_dir.is_dir()
        else []
    )
    report = {}
    for label, spec in BIOS_REQUIREMENTS.items():
        patterns, wanted_size = spec["patterns"], spec["size"]
        found = []
        for name, size in files:
            if not any(fnmatch(name.lower(), p.lower()) for p in patterns):
                continue
            if wanted_size is not None:
                if abs(size - wanted_size) > wanted_size * _SIZE_TOLERANCE:
                    continue
            found.append(name)
        report[label] = {
            "required": patterns,
            "found": sorted(found),
            "satisfied": bool(found),
        }
    return report


def build_report(docs_dir: Path, roms_root: Path, bios_dir: Path) -> dict:
    """The whole picture, as data. Rendering is the caller's problem."""
    systems = parse_guide(docs_dir)
    on_disk = scan_roms(roms_root)

    per_system = []
    for entry in systems:
        filenames = []
        for folder in entry["folders"]:
            filenames.extend(on_disk.get(folder, []))
        present, unclear = match_titles(entry["titles"], filenames)
        per_system.append(
            {
                "system": entry["system"],
                "folders": entry["folders"],
                # JoiPlay's fangames live outside `ROMs/` and arrive as
                # folders rather than files, so this scanner cannot see them.
                # Flagged rather than reported as zero: an empty count next to
                # a full checklist reads as "nothing installed", which would be
                # this script inventing an absence out of its own blind spot.
                "scannable": bool(entry["folders"]),
                "files_present": len(filenames),
                "listed": len(entry["titles"]),
                "likely_present": present,
                "not_obviously_present": unclear,
            }
        )

    return {
        "bios": check_bios(bios_dir),
        "systems": per_system,
        "totals": {
            "files": sum(s["files_present"] for s in per_system),
            "listed": sum(s["listed"] for s in per_system),
            "unscannable": sum(1 for s in per_system if not s["scannable"]),
        },
    }


def render(report: dict) -> str:
    """The report as something a person reads at a terminal."""
    out = []
    bios = report["bios"]
    missing_bios = [k for k, v in bios.items() if not v["satisfied"]]
    out.append("BIOS")
    for label, info in bios.items():
        mark = "OK  " if info["satisfied"] else "--  "
        detail = (
            ", ".join(info["found"])
            if info["found"]
            else f"expected {' or '.join(info['required'])}"
        )
        out.append(f"  {mark}{label}: {detail}")

    out.append("")
    out.append("Games on disk, per system")
    for entry in report["systems"]:
        if not entry["scannable"]:
            out.append(
                f"    --  {entry['system']}  ({entry['listed']} listed) — not"
                f" scanned: its files live outside ROMs/"
            )
            continue
        out.append(
            f"  {entry['files_present']:>3} file(s)  {entry['system']}"
            f"  ({len(entry['likely_present'])}/{entry['listed']} of the"
            f" checklist recognised)"
        )
        for title in entry["not_obviously_present"]:
            out.append(f"        · {title}")

    totals = report["totals"]
    out.append("")
    out.append(
        f"{totals['files']} file(s) across {len(report['systems'])} systems; "
        f"the guide lists {totals['listed']} titles."
    )
    if missing_bios:
        out.append(f"{len(missing_bios)} BIOS requirement(s) unmet.")
    out.append("")
    out.append(
        "Titles listed under a system are ones this script did not recognise "
        "among the filenames.\nThat is a guess, not an inventory: a dump can "
        "be named anything. Check before concluding\nanything is missing."
    )
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--docs", required=True, type=Path)
    parser.add_argument("--roms", required=True, type=Path)
    parser.add_argument("--bios", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="machine-readable")
    args = parser.parse_args(argv)

    report = build_report(args.docs, args.roms, args.bios)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
