#!/usr/bin/env python3
"""Interactive data curation for the be_water catalog.

Phase 3 — verification sign-off. Lists fichas eligible to be verified (a label
photo on file + at least one label-confirmed value) and lets an admin freeze
each after reviewing the label. Verifying locks the ficha against overwrite;
non-label values keep their "fabricante" / "a mano" provenance.

    bazel run //packages/be_water/scripts:audit_data

Runs locally against be-water-app via ADC. Writes directly to Firestore on
each sign-off (idempotent)."""

import argparse
import os
import webbrowser

os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

from packages.be_water.web import data_audit, repository  # noqa: E402
from packages.be_water.web.domain import MINERAL_LABELS  # noqa: E402


def _prompt(text: str) -> str:
    try:
        return input(text).strip()
    except EOFError:
        return "q"


def _fields_summary(water) -> str:
    label = ", ".join(MINERAL_LABELS.get(f, f) for f in water.verified_fields)
    other = [f for f in water.minerals if f not in water.verified_fields]
    other_str = ", ".join(MINERAL_LABELS.get(f, f) for f in other) or "—"
    return f"    etiqueta: {label}\n    resto (fabricante/a mano): {other_str}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-open", action="store_true", help="don't open the label in the browser"
    )
    args = parser.parse_args()

    waters = repository.get_all_waters()
    todo = [w for w in waters if data_audit.verifiable(w)]
    verified = sum(w.verified for w in waters)
    print(
        f"\n{len(waters)} fichas · {verified} verificadas · "
        f"{len(todo)} elegibles para firmar\n"
    )
    if not todo:
        print("Nada que firmar.\n")
        return

    signed = 0
    for i, water in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {water.id} — {water.name}")
        print(_fields_summary(water))
        print(f"    etiqueta: {water.label_photo_url}")
        if not args.no_open:
            webbrowser.open(water.label_photo_url)
        answer = _prompt(
            "    Revisa la etiqueta. ¿[v]erificar y bloquear / [s]altar / [q]salir? "
        ).lower()
        if answer == "q":
            break
        if answer == "v":
            data_audit.mark_verified(water)
            signed += 1
            print("    → verificada y bloqueada.\n")
        else:
            print("    saltada.\n")

    print(f"\n{signed} fichas firmadas.\n")


if __name__ == "__main__":
    main()
