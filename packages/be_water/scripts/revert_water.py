#!/usr/bin/env python3
"""Undo a contribution that overwrote a water's composition (ADC, be-water-app).

Every save that changes an existing ficha's minerals snapshots the previous
document first, so a bad edit is recoverable without digging through logs:

    bazel run //packages/be_water/scripts:revert_water                # list all
    bazel run //packages/be_water/scripts:revert_water -- penaclara   # one water

Reverting writes the snapshot back verbatim and drops it from the trail. Every
write is behind a confirmation."""

import argparse
import os

os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

from packages.be_water.web import repository  # noqa: E402
from packages.be_water.web.domain import MINERAL_LABELS, Water  # noqa: E402

_REASONS = {
    "older_analysis": "⏳ análisis más antiguo que el que había",
    "composition_changed": "✏️  composición modificada",
}


def _prompt(text: str) -> str:
    try:
        return input(text).strip()
    except EOFError:
        return "q"


def _diff(previous: dict, current: Water) -> list[str]:
    """Field-by-field differences between the snapshot and what is live now."""
    before = previous.get("minerals") or {}
    after = current.minerals
    lines = []
    for field in sorted(set(before) | set(after)):
        old, new = before.get(field), after.get(field)
        if old != new:
            label = MINERAL_LABELS.get(field, field)
            lines.append(
                f"    {label}: {old if old is not None else '—'} "
                f"→ {new if new is not None else '—'}"
            )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("water_id", nargs="?", help="only this water")
    args = parser.parse_args()

    revisions = repository.list_revisions(args.water_id)
    print(f"\n{len(revisions)} instantáneas guardadas.\n")
    if not revisions:
        print("Nada que revertir.\n")
        return

    for revision_id, data in revisions:
        previous = data.get("previous") or {}
        water_id = data.get("water_id", "?")
        current = repository.get_water(water_id)
        if current is None:
            print(f"{water_id} — la ficha ya no existe; instantánea huérfana.")
            continue
        reason = _REASONS.get(data.get("reason", ""), data.get("reason", "?"))
        print(f"{water_id} — {previous.get('name', water_id)}")
        print(
            f"    guardada {data.get('saved_at')} · por "
            f"{data.get('replaced_by', '?')} · {reason}"
        )
        print(
            f"    análisis: {previous.get('analysis_date') or 'sin fecha'} "
            f"→ {current.analysis_date or 'sin fecha'}"
        )
        changes = _diff(previous, current)
        print("\n".join(changes) if changes else "    (sin cambios en minerales)")

        answer = _prompt("    ¿[r]evertir / [s]altar / [q]salir? ").lower()
        if answer == "q":
            break
        if answer != "r":
            print()
            continue
        repository.save_water(Water.from_firestore(water_id, previous))
        repository.delete_revision(revision_id)
        print(f"    ✓ {water_id} restaurada.\n")


if __name__ == "__main__":
    main()
