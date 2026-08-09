#!/usr/bin/env python3
"""Suggest next season's draft order from the ending season's palmarés.

The draft order is the reverse of the final classification, so the table
written by `fetch_palmares.py` already contains the answer. This only reads it
and prints the reversal — copying it by hand is where the order drifts, and a
wrong order does not fail loudly, it just makes people pick out of turn for
fifteen rounds.

It is a *suggestion*: the reglamento adjusts the order for newcomers, and that
adjustment cannot be derived from the standings. Confirm with the user before
editing `packages.biwenger_tools.constants.DRAFT_ORDER_NAMES`.

Needs ADC against the project hosting the palmarés Firestore:

    gcloud auth application-default login
    python3 .claude/skills/season-rollover/scripts/suggest_draft_order.py 25-26
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))

from packages.biwenger_tools.constants import (  # noqa: E402
    LEAGUE_MEMBERS,
    NON_PLAYING_MEMBER_IDS,
)  # noqa: E402
from core.sdk.firestore import get_document  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", help='Ending season, e.g. "25-26"')
    args = parser.parse_args()

    doc = get_document("palmares", args.season)
    if not doc:
        print(f"No hay documento palmares/{args.season}.", file=sys.stderr)
        print("Ejecuta antes fetch_palmares.py (Step 2b).", file=sys.stderr)
        return 1

    table = doc.get("standings_table") or []
    if not table:
        print(f"palmares/{args.season} no tiene standings_table.", file=sys.stderr)
        return 1

    rows = sorted(table, key=lambda r: r.get("position", 0))
    print(f"Clasificación final {args.season}:")
    for row in rows:
        name = LEAGUE_MEMBERS.get(row.get("user_id"), row.get("real_name") or "?")
        print(f"  {row.get('position'):>2}. {name}")

    # Abandoned accounts are stored with `user_id=0`, so the id alone cannot
    # tell a spectator apart — match on the resolved name too.
    non_playing = {LEAGUE_MEMBERS[i] for i in NON_PLAYING_MEMBER_IDS}
    ranked = [
        LEAGUE_MEMBERS.get(r.get("user_id"), r.get("real_name") or "?") for r in rows
    ]
    suggested = [n for n in reversed(ranked) if n not in non_playing]

    print("\nInverso a la clasificación:")
    for i, name in enumerate(suggested, 1):
        print(f"  {i}. {name}")

    current = {n for i, n in LEAGUE_MEMBERS.items() if i not in NON_PLAYING_MEMBER_IDS}
    newcomers = sorted(current - set(suggested))
    departed = sorted(set(suggested) - current)

    if departed:
        print(f"\n⚠️  Ya no están en LEAGUE_MEMBERS: {', '.join(departed)}")
        suggested = [n for n in suggested if n not in departed]

    if newcomers:
        # Reglamento: a newcomer has no previous classification to invert, so
        # the order places them in the middle rather than at either end.
        middle = len(suggested) // 2
        suggested = suggested[:middle] + newcomers + suggested[middle:]
        print(f"\n⚠️  Sin clasificación previa: {', '.join(newcomers)}")
        print("    Colocados en el medio, según el reglamento.")

    print("\nOrden final propuesto:")
    for i, name in enumerate(suggested, 1):
        print(f"  {i}. {name}")

    print("\nPara core/constants.py:")
    print("DRAFT_ORDER_NAMES: tuple[str, ...] = (")
    for name in suggested:
        print(f'    "{name}",')
    print(")")
    print(
        "\nRevísalo con el usuario: el reglamento ajusta el orden para los que "
        "entran nuevos, y eso no sale de la clasificación."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
