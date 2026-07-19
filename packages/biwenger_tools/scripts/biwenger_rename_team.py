#!/usr/bin/env python3
"""Rename a team across clausulazos + rebuild tabla_justicia for a season.

When an account is deleted mid-season Biwenger emits a placeholder like
``Usuario`` in the transfer board, which the scraper persists verbatim
into ``clausulazos/{season}/transfers``. This script rewrites every
occurrence of ``--old`` to ``--new`` in both ``equipo_vendedor`` and
``equipo_comprador`` and then recomputes ``tabla_justicia/{season}/teams``
from the corrected clausulazos so the per-team aggregates stay consistent.

Default is dry-run; pass ``--apply`` to actually write to Firestore.

Usage::

    python3 scripts/biwenger_rename_team.py 25-26 \\
        --old Usuario --new '#NOALOSCLAUSULAZOS' [--apply]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from core.domain.models import Clausulazo  # noqa: E402
from core.sdk.firestore import get_client  # noqa: E402
from packages.biwenger_tools.scraper_job.logic.processing import (  # noqa: E402
    build_tabla_justicia,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", help="Season key, e.g. 25-26")
    parser.add_argument("--old", required=True, help="Name to replace.")
    parser.add_argument("--new", required=True, help="Replacement name.")
    parser.add_argument("--apply", action="store_true", help="Write Firestore.")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] Rename {args.old!r} → {args.new!r} for {args.season}\n")

    client = get_client()
    coll = client.collection(f"clausulazos/{args.season}/transfers")

    # --- Step 1: rewrite affected clausulazos ---
    pending = []
    for snap in coll.stream():
        data = snap.to_dict() or {}
        updates: dict = {}
        if data.get("equipo_vendedor") == args.old:
            updates["equipo_vendedor"] = args.new
        if data.get("equipo_comprador") == args.old:
            updates["equipo_comprador"] = args.new
        if updates:
            pending.append((snap, data, updates))

    print(f"{len(pending)} clausulazo docs to update.")
    for snap, data, updates in pending:
        print(
            f"  {str(data.get('fecha', ''))[:19]:20s}  {snap.id[:12]}  "
            f"{data.get('jugador'):20s}  {updates}"
        )

    if args.apply:
        for snap, _, updates in pending:
            snap.reference.update(updates)
        print(f"\nUpdated {len(pending)} clausulazo docs.")
    else:
        print("\n(dry-run) skipping clausulazo updates.")

    # --- Step 2: rebuild tabla_justicia from the corrected clausulazos ---
    all_clausulazos = [
        Clausulazo.from_firestore(snap.id, snap.to_dict() or {})
        for snap in coll.stream()
    ]
    tabla = build_tabla_justicia(all_clausulazos)

    print(f"\nNew tabla_justicia ({len(tabla)} teams):")
    for entry in sorted(tabla, key=lambda e: -e.total_hechos):
        print(
            f"  {entry.equipo:30s}  hechos={entry.total_hechos:3d}  "
            f"recibidos={entry.total_recibidos:3d}  "
            f"mira={entry.punto_de_mira!r}  agresor={entry.mayor_agresor!r}"
        )

    if args.apply:
        justice_coll = client.collection(f"tabla_justicia/{args.season}/teams")
        existing = list(justice_coll.stream())
        for snap in existing:
            snap.reference.delete()
        for entry in tabla:
            justice_coll.document(entry.equipo).set(entry.to_firestore())
        print(
            f"\nWiped {len(existing)} existing tabla_justicia docs; "
            f"wrote {len(tabla)} fresh ones."
        )
    else:
        print("\n(dry-run) skipping tabla_justicia rebuild.")

    print("\nDone.")


if __name__ == "__main__":
    main()
