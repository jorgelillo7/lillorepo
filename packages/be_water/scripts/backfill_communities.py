#!/usr/bin/env python3
"""One-shot backfill of ``Water.community`` for existing catalog docs.

The place search matches a water's province *or* its community, so a ficha
saved with a province and no community is invisible to every community-level
search. Derives the community from the province (see web/geo.py).

Idempotent — only fills gaps, never overwrites a stated community. Dry-run by
default; pass --apply to write.

    bazel run //packages/be_water/scripts:backfill_communities             # preview
    bazel run //packages/be_water/scripts:backfill_communities -- --apply  # write

Read the *unresolved* tail before applying: a province the geo table does not
know (a typo, or a spelling missing from ``_PROVINCE_ALIASES``) leaves the
water exactly as invisible as it was, and a run that only reports what it
fixed hides them.

Runs locally against be-water-app via ADC."""

import argparse
import os
from collections import defaultdict

os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

from packages.be_water.web import geo, repository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to Firestore")
    args = parser.parse_args()

    waters = repository.get_all_waters()
    gaps = [w for w in waters if not w.community]
    filled = 0
    unresolved: dict[str, list[str]] = defaultdict(list)

    for water in gaps:
        community = geo.community_of(water.province)
        if not community:
            unresolved[water.province or "(sin provincia)"].append(water.id)
            continue
        filled += 1
        print(f"  {water.id}: {water.province} → {community}")
        if args.apply:
            repository.set_water_community(water.id, community)

    verb = "actualizadas" if args.apply else "cambiarían (dry-run)"
    print(f"\n{filled}/{len(waters)} fichas {verb}.")

    if unresolved:
        total = sum(len(ids) for ids in unresolved.values())
        print(f"\n⚠️  {total} sin resolver — siguen invisibles a la búsqueda:")
        for province, ids in sorted(unresolved.items()):
            print(f"  {province}: {', '.join(sorted(ids))}")
        print("Corrige la provincia (o añade el alias en geo.py) y repite.")

    if not args.apply and filled:
        print("\nRepite con --apply para escribir.")


if __name__ == "__main__":
    main()
