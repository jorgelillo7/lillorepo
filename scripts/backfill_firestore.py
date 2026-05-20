#!/usr/bin/env python3
"""One-shot backfill: legacy CSVs → Firestore.

Reads the league CSVs (the same files the scraper uploads to Google Drive)
and bulk-writes them to the Firestore collections the web app will read.

Idempotent: every target collection is wiped and rewritten on each run, so
re-running is safe and produces the same result. Doc ids are natural keys
(id_hash / autor / equipo / temporada) except clausulazos, which have no
natural key and use a deterministic content hash.

Collections written:

    comunicados/{season}/messages/{id_hash}
    participacion/{season}/authors/{autor}
    clausulazos/{season}/transfers/{content_hash}
    tabla_justicia/{season}/teams/{equipo}
    palmares/{temporada}

Usage (from the repo root):

    gcloud auth application-default login          # once, sets up ADC
    python3 scripts/backfill_firestore.py --csv-dir ~/Downloads/Biwenger

    # dry run — parse and report counts, write nothing:
    python3 scripts/backfill_firestore.py --dry-run
"""

import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path

# Make `core.*` importable when run as a plain script from the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

DEFAULT_PROJECT = "biwenger-tools"
DEFAULT_CSV_DIR = "~/Downloads/Biwenger"


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _clausulazo_id(row: dict) -> str:
    """Deterministic doc id for a clausulazo — content hash, so re-runs map
    a given transfer to the same document."""
    raw = "|".join(
        str(row.get(k, ""))
        for k in ("fecha", "jugador", "equipo_vendedor", "equipo_comprador", "precio")
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _discover(csv_dir: Path, base: str) -> dict[str, Path]:
    """Map season → csv path for files named `{base}_{season}.csv`."""
    found = {}
    for path in sorted(csv_dir.glob(f"{base}_*.csv")):
        season = path.stem[len(base) + 1 :]
        found[season] = path
    return found


def backfill(csv_dir: Path, dry_run: bool) -> int:
    """Run the backfill. Returns a process exit code (0 on full parity)."""
    from core.domain.models import (
        Clausulazo,
        JusticeEntry,
        LeagueMessage,
        Palmares,
        Participation,
    )
    from core.sdk import firestore

    mismatches = 0

    def _write(collection: str, pairs: list[tuple[str, dict]], expected: int) -> None:
        """Wipe + rewrite a collection, then verify the doc count."""
        nonlocal mismatches
        if dry_run:
            print(f"  [dry-run] {collection}: would write {len(pairs)} docs")
            return
        deleted = firestore.delete_collection(collection)
        written = firestore.batch_write(collection, pairs)
        actual = firestore.count(collection)
        ok = actual == expected == written
        flag = "OK" if ok else "MISMATCH"
        print(
            f"  {collection}: cleared {deleted}, wrote {written}, "
            f"count {actual}, expected {expected}  [{flag}]"
        )
        if not ok:
            mismatches += 1

    # --- comunicados -------------------------------------------------------
    for season, path in _discover(csv_dir, "comunicados").items():
        rows = _read_csv(path)
        msgs = [LeagueMessage.from_csv_row(r) for r in rows]
        pairs = [(m.id_hash, m.to_firestore()) for m in msgs if m.id_hash]
        _write(f"comunicados/{season}/messages", pairs, len(pairs))

    # --- participacion -----------------------------------------------------
    for season, path in _discover(csv_dir, "participacion").items():
        rows = _read_csv(path)
        parts = [Participation.from_csv_row(r) for r in rows]
        pairs = [(p.autor, p.to_firestore()) for p in parts if p.autor]
        _write(f"participacion/{season}/authors", pairs, len(pairs))

    # --- clausulazos -------------------------------------------------------
    for season, path in _discover(csv_dir, "clausulazos").items():
        rows = _read_csv(path)
        pairs = [
            (_clausulazo_id(r), Clausulazo.from_csv_row(r).to_firestore())
            for r in rows
        ]
        _write(f"clausulazos/{season}/transfers", pairs, len(pairs))

    # --- tabla_justicia ----------------------------------------------------
    for season, path in _discover(csv_dir, "tabla_justicia").items():
        rows = _read_csv(path)
        entries = [JusticeEntry.from_csv_row(r) for r in rows]
        pairs = [(e.equipo, e.to_firestore()) for e in entries if e.equipo]
        _write(f"tabla_justicia/{season}/teams", pairs, len(pairs))

    # --- palmares (single flat CSV, multi-row per season) ------------------
    palmares_path = csv_dir / "palmares.csv"
    if palmares_path.exists():
        rows = _read_csv(palmares_path)
        seasons = Palmares.from_csv_rows(rows)
        pairs = [(p.temporada, p.to_firestore()) for p in seasons]
        _write("palmares", pairs, len(pairs))
    else:
        print(f"  palmares.csv not found in {csv_dir} — skipped")

    return 1 if mismatches else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv-dir",
        default=DEFAULT_CSV_DIR,
        help=f"Directory holding the league CSVs (default: {DEFAULT_CSV_DIR})",
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"GCP project hosting Firestore (default: {DEFAULT_PROJECT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse the CSVs and report counts without writing to Firestore",
    )
    args = parser.parse_args()

    csv_dir = Path(args.csv_dir).expanduser()
    if not csv_dir.is_dir():
        print(f"ERROR: csv dir not found: {csv_dir}", file=sys.stderr)
        return 2

    os.environ.setdefault("FIRESTORE_PROJECT", args.project)

    print(f"Backfill source : {csv_dir}")
    print(f"Firestore project: {args.project}")
    print(f"Mode             : {'DRY RUN' if args.dry_run else 'WRITE'}")
    print("-" * 60)

    code = backfill(csv_dir, args.dry_run)

    print("-" * 60)
    print("Backfill complete." if code == 0 else "Backfill finished WITH MISMATCHES.")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
