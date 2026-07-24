#!/usr/bin/env python3
"""One-shot backfill of ``Water.sources`` for existing catalog docs.

Derives the provenance of every non-label field (see web/provenance.py):
minerals not confirmed from a label → "manufacturer" for seed-origin waters,
"manual" otherwise; province/community → "AESAN" when the registry agrees.

Idempotent — only fills gaps. Dry-run by default; pass --apply to write.

    bazel run //packages/be_water/scripts:backfill_sources             # preview
    bazel run //packages/be_water/scripts:backfill_sources -- --apply  # write

Runs locally against be-water-app via ADC."""

import argparse
import os

os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

from packages.be_water.web import provenance, repository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to Firestore")
    args = parser.parse_args()

    waters = repository.get_all_waters()
    changed = 0
    for water in waters:
        new_sources = provenance.derive_sources(water)
        if new_sources == water.sources:
            continue
        changed += 1
        added = {k: v for k, v in new_sources.items() if k not in water.sources}
        print(f"  {water.id}: +{added}")
        if args.apply:
            repository.set_water_sources(water.id, new_sources)

    verb = "actualizadas" if args.apply else "cambiarían (dry-run)"
    print(f"\n{changed}/{len(waters)} fichas {verb}.")
    if not args.apply and changed:
        print("Repite con --apply para escribir.")


if __name__ == "__main__":
    main()
