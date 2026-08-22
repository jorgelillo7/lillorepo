#!/usr/bin/env python3
"""Regenerate the recognised-waters snapshot for Spain from the official list.

AESAN used to publish Spain's list as its own PDF. That document, and the whole
`/AECOSAN/` tree it lived under, now 404: the agency points instead at the
consolidated list the Commission publishes under Article 1 of Directive
2009/54/EC, whose "recognised by Spain" section is the same registry. Run this
manually (or from a Claude session) every few months:

    pip3 install pypdf   # one-time, local only — not a Bazel dep
    python3 packages/be_water/scripts/refresh_aesan_snapshot.py

A non-empty `git diff` on the snapshot IS the news: waters Spain has recognised
(or dropped) since the last refresh.
"""

import io
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PDF_URL = (
    "https://food.ec.europa.eu/document/download/"
    "ec4fbcc0-7185-4dce-820a-27f7e2653dad_en"
    "?filename=labelling-nutrition_mineral-waters_list_eu-recognised.pdf"
)
SNAPSHOT_PATH = Path("packages/be_water/web/aesan_snapshot.py")

# Spain's own table, and the third-country one that follows it (out of scope:
# those waters are recognised by Spain but sourced abroad).
_SPAIN = "natural mineral waters recognised by Spain"
_THIRD = "from third countries recognised by Spain"
_OTHER = re.compile(r"List of natural mineral waters.*recognised by (?!Spain)")
_HEADER = re.compile(r"Trade [Dd]escription\s+Name of source\s+Place")
_UPDATED = re.compile(r"Last update\s+(\d{2})\.(\d{2})\.(\d{4})")
# A run of non-space text ending where two or more spaces begin: one table cell
# in pypdf's layout mode, which preserves the PDF's own column positions.
_CELL = re.compile(r"\S(?:.*?\S)?(?=\s{2,}|$)")
# Every place reads "Municipality (Province)" — the closing parenthesis is what
# tells a wrapped cell from a finished one.
_PROVINCE = re.compile(r"^(.*)\(([^)]+)\)\s*$")


def _is_noise(line: str) -> bool:
    return not line.strip() or "Last update" in line or bool(_HEADER.search(line))


def _spain_lines(pages: list[str]) -> tuple[list[tuple[int, str]], str]:
    """Spain's table rows as (page number, line), plus the document's date."""
    picked: list[tuple[int, str]] = []
    date = "?"
    state = None
    for number, page in enumerate(pages):
        for line in page.split("\n"):
            if m := _UPDATED.search(line):
                date = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
            if _THIRD in line or _OTHER.search(line):
                state = None
                continue
            if _SPAIN in line:
                state = "spain"
                continue
            if state and not _is_noise(line):
                picked.append((number, line.rstrip()))
    return picked, date


def _column_starts(picked: list[tuple[int, str]]) -> dict[int, tuple[int, int]]:
    """Where columns 2 and 3 begin, per page — the layout shifts between them.

    Columns are left-aligned, so the leftmost start across a page's complete
    rows is the boundary. The mode would sit too far right and clip the first
    character of the next cell onto the previous one.
    """
    per_page: dict[int, list[tuple[int, int]]] = {}
    for number, line in picked:
        cells = [m.start() for m in _CELL.finditer(line)]
        if len(cells) == 3:
            per_page.setdefault(number, []).append((cells[1], cells[2]))
    return {
        number: (min(a for a, _ in pairs), min(b for _, b in pairs))
        for number, pairs in per_page.items()
        if pairs
    }


def parse(pdf_bytes: bytes) -> tuple[str, list[dict]]:
    # Imported here, not at module scope: pypdf is a local-only pip install
    # (deliberately not a Bazel dep, to keep it out of the runtime image), and
    # `parse_pages` must stay importable from the tests without it.
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return parse_pages(
        [page.extract_text(extraction_mode="layout") or "" for page in reader.pages]
    )


def parse_pages(pages: list[str]) -> tuple[str, list[dict]]:
    """Layout-mode text, one string per page → (date, Spain's entries).

    Split from `parse` so the column and wrapping rules are testable without a
    PDF: they are where every past regression lived.
    """
    picked, date = _spain_lines(pages)
    starts = _column_starts(picked)
    usable = [(n, ln) for n, ln in picked if n in starts]

    entries: list[dict] = []
    pending: dict[str, list[str]] = {"spring": [], "place": []}
    index = 0
    while index < len(usable):
        number, line = usable[index]
        first, second, third = _split(line, starts[number])
        index += 1
        if not first:
            # A cell that wraps renders its overflow above the row it belongs
            # to, so keep it until the row itself arrives.
            for key, value in (("spring", second), ("place", third)):
                if value:
                    pending[key].append(value)
            continue

        spring = pending["spring"] + ([second] if second else [])
        place = pending["place"] + ([third] if third else [])
        pending = {"spring": [], "place": []}
        # ...except a three-line cell, which overflows downwards instead. The
        # province's closing parenthesis is the only reliable end-of-row mark.
        while not _PROVINCE.match(" ".join(place)) and index < len(usable):
            next_number, next_line = usable[index]
            more_first, more_second, more_third = _split(next_line, starts[next_number])
            if more_first:
                break
            if more_second:
                spring.append(more_second)
            if more_third:
                place.append(more_third)
            index += 1

        joined = " ".join(place)
        match = _PROVINCE.match(joined)
        entries.append(
            {
                "name": first,
                "spring": " ".join(spring),
                "place": (match.group(1) if match else joined).strip(),
                "province": match.group(2).strip() if match else "",
            }
        )
    return date, entries


def _split(line: str, starts: tuple[int, int]) -> tuple[str, str, str]:
    second, third = starts
    return line[:second].strip(), line[second:third].strip(), line[third:].strip()


def _download() -> bytes:
    try:
        body = urllib.request.urlopen(PDF_URL, timeout=120).read()
    except urllib.error.URLError:
        # Python's bundled CA store doesn't know corporate MITM certs;
        # curl uses the system trust store and does.
        body = subprocess.run(
            ["curl", "-sSL", PDF_URL], check=True, capture_output=True, timeout=180
        ).stdout
    # A dead link is the failure mode that actually happens: the old AESAN URL
    # answered 404 with a 107 KB HTML page, and pypdf reported it as a
    # truncated stream. Check the bytes, not the status — an error page served
    # as 200 after a redirect would pass a status check.
    if not body.startswith(b"%PDF"):
        sys.exit(
            f"{PDF_URL}\nreturned {len(body)} bytes that are not a PDF — the "
            "document has probably moved. Find it from "
            "https://food.ec.europa.eu/food-safety/labelling-and-nutrition"
            "/natural-mineral-waters-and-spring-water_en"
        )
    return body


def main() -> None:
    date, entries = parse(_download())
    if len(entries) < 100:
        sys.exit(
            f"Only {len(entries)} entries parsed — the PDF layout probably "
            "changed; refusing to overwrite the snapshot."
        )
    if missing := [e["name"] for e in entries if not e["province"]]:
        sys.exit(
            f"No province parsed for {missing} — a wrapped row was read wrong; "
            "refusing to overwrite the snapshot."
        )
    entries.sort(key=lambda e: (e["name"].lower(), e["spring"].lower()))
    lines = [
        '"""Natural mineral waters recognised by Spain — generated snapshot.',
        "",
        "Do not edit by hand — regenerate with:",
        "    python3 packages/be_water/scripts/refresh_aesan_snapshot.py",
        "A git diff here means Spain recognised (or dropped) waters.",
        '"""',
        "",
        f'AESAN_VERSION = "EU/{date[-4:]}-{date[3:5]}-{date[:2]}"',
        f'AESAN_DATE = "{date}"',
        "",
        "AESAN_WATERS = [",
    ]
    for e in entries:
        lines.append(
            f'    {{"name": {e["name"]!r}, "spring": {e["spring"]!r}, '
            f'"place": {e["place"]!r}, "province": {e["province"]!r}}},'
        )
    lines.append("]")
    SNAPSHOT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # The generated file must pass the repo linters (88-col black style).
    subprocess.run(["black", "--quiet", str(SNAPSHOT_PATH)], check=True)
    print(f"{date}: {len(entries)} waters → {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
