#!/usr/bin/env python3
"""One-shot backfill: every dated water's current composition becomes the first
entry of its analysis series.

Without this the series is empty on the day it ships, so the ficha's selector
never appears until someone uploads a second label — and the first analysis of
every water would be the only one never recorded.

Only waters with an `analysis_date` are touched: an undated composition has no
place on a timeline, which is the whole rule (three quarters of the catalog is
in that state — the label is not required to print the date).

Idempotent: the entry id is `{water_id}__{analysis_date}`, so re-running writes
the same document. Dry-run by default; pass --apply to write.

    bazel run //packages/be_water/scripts:backfill_analyses             # preview
    bazel run //packages/be_water/scripts:backfill_analyses -- --apply  # write

Runs locally against be-water-app via ADC."""

import argparse
import os

os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

from packages.be_water.web import repository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to Firestore")
    args = parser.parse_args()

    waters = repository.get_all_waters()
    dated = [w for w in waters if w.analysis_date]
    written = 0

    for water in dated:
        existing = repository.get_analysis(water.id, water.analysis_date)
        state = "ya existe" if existing else "nueva"
        print(
            f"  {water.id:28s} {water.analysis_date:8s} "
            f"{len(water.minerals):2d} minerales  ({state})"
        )
        if args.apply and not existing:
            repository.save_analysis(water)
            written += 1

    undated = len(waters) - len(dated)
    print(
        f"\n{len(dated)} aguas con fecha, {undated} sin fecha (no entran, por diseño)"
    )
    if args.apply:
        print(f"{written} entradas escritas")
    else:
        print("dry-run — nada escrito; pasa --apply para hacerlo")


if __name__ == "__main__":
    main()
