#!/usr/bin/env python3
"""Wipe a draft season's picks and turn state, keeping the manager roster.

Run between a rehearsal and the real draft, and again at the season rollover.
The `managers` collection is preserved by default on purpose: those bindings
are the `/soy` roll-call, and making seven people repeat it minutes before the
draft is exactly the friction the bot exists to remove. Pass `--managers` to
drop them too.

Requires ADC against the project hosting the draft Firestore:

    gcloud auth application-default login

    python3 packages/biwenger_tools/scripts/draft/reset.py --season 26-27
    python3 packages/biwenger_tools/scripts/draft/reset.py \
        --season 26-27 --apply
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.sdk import firestore as fs  # noqa: E402


def _collections(season: str, include_managers: bool) -> list[str]:
    paths = [f"draft/{season}/picks", f"draft/{season}/state"]
    if include_managers:
        paths.append(f"draft/{season}/managers")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True, help='Season key, e.g. "26-27"')
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete. Without it the script only reports what it would do.",
    )
    parser.add_argument(
        "--managers",
        action="store_true",
        help="Also drop the /soy registrations (everyone must register again).",
    )
    args = parser.parse_args()

    total = 0
    for path in _collections(args.season, args.managers):
        doc_ids = [doc_id for doc_id, _ in fs.list_documents(path)]
        total += len(doc_ids)
        print(f"{path}: {len(doc_ids)} documentos")
        if not args.apply:
            continue
        for doc_id in doc_ids:
            fs.delete_document(path, doc_id)
        print(f"  borrados {len(doc_ids)}")

    if not args.apply:
        print(f"\nEn seco: {total} documentos se borrarían. Repite con --apply.")
    else:
        print(f"\nBorrados {total} documentos de la temporada {args.season}.")
        if not args.managers:
            print("Los registros de /soy se han conservado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
