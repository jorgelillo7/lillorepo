#!/usr/bin/env python3
"""Regenerate the AESAN recognised-waters snapshot from the official PDF.

Downloads the "Lista de aguas minerales naturales oficialmente reconocidas
por España" and rewrites packages/be_water/web/aesan_snapshot.py. Run it
manually (or from a Claude session) every few months:

    pip3 install pypdf   # one-time, local only — not a Bazel dep
    python3 packages/be_water/scripts/refresh_aesan_snapshot.py

A non-empty `git diff` on the snapshot IS the news: waters AESAN has
recognised (or dropped) since the last refresh.
"""

import io
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from pypdf import PdfReader

PDF_URL = (
    "https://www.aesan.gob.es/AECOSAN/docs/documentos/"
    "seguridad_alimentaria/gestion_riesgos/lista_espanola.pdf"
)
SNAPSHOT_PATH = Path("packages/be_water/web/aesan_snapshot.py")

# Every entry's last column ends in "(Provincia)". Multi-line entries wrap
# the place column, so lines are accumulated until that pattern closes.
_ENTRY_END = re.compile(r"\(([^)]+)\)\s*$")
_VERSION = re.compile(r"Versi.n\s+(AMN/\d+)")
_DATE = re.compile(r"(\d{2}/\d{2}/\d{4})")
_HEADER_NOISE = (
    "Lista de aguas",
    "Nombre Comercial",
    "Página",
)


def parse(pdf_bytes: bytes) -> tuple[str, str, list[dict]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    version, date = "?", "?"
    entries = []
    pending = ""
    for page in reader.pages:
        for line in page.extract_text().splitlines():
            line = line.strip()
            if not line:
                continue
            if m := _VERSION.search(line):
                version = m.group(1)
                if d := _DATE.search(line):
                    date = d.group(1)
                continue
            if any(noise in line for noise in _HEADER_NOISE):
                continue
            pending = f"{pending} {line}".strip() if pending else line
            if not _ENTRY_END.search(pending):
                continue  # place column wrapped to the next line
            province = _ENTRY_END.search(pending).group(1).strip()
            # Columns are separated by 2+ spaces in the extracted text.
            columns = re.split(r"\s{2,}", _ENTRY_END.sub("", pending).strip())
            pending = ""
            if len(columns) < 2:
                continue  # stray header/footer fragment
            entries.append(
                {
                    "name": columns[0].strip(),
                    "spring": columns[1].strip(),
                    "place": " ".join(c.strip() for c in columns[2:]).strip(),
                    "province": province,
                }
            )
    return version, date, entries


def _download() -> bytes:
    try:
        return urllib.request.urlopen(PDF_URL, timeout=60).read()
    except urllib.error.URLError:
        # Python's bundled CA store doesn't know corporate MITM certs;
        # curl uses the system trust store and does.
        return subprocess.run(
            ["curl", "-sSL", PDF_URL], check=True, capture_output=True, timeout=120
        ).stdout


def main() -> None:
    pdf_bytes = _download()
    version, date, entries = parse(pdf_bytes)
    if len(entries) < 100:
        sys.exit(
            f"Only {len(entries)} entries parsed — the PDF layout probably "
            "changed; refusing to overwrite the snapshot."
        )
    entries.sort(key=lambda e: (e["name"].lower(), e["spring"].lower()))
    lines = [
        '"""AESAN recognised natural mineral waters — generated snapshot.',
        "",
        "Do not edit by hand — regenerate with:",
        "    python3 packages/be_water/scripts/refresh_aesan_snapshot.py",
        "A git diff here means AESAN recognised (or dropped) waters.",
        '"""',
        "",
        f'AESAN_VERSION = "{version}"',
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
    print(f"{version} ({date}): {len(entries)} waters → {SNAPSHOT_PATH}")


if __name__ == "__main__":
    main()
