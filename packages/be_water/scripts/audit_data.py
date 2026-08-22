#!/usr/bin/env python3
"""Interactive data curation for the be_water catalog.

Three read-then-repair passes over the live catalog (ADC, be-water-app):

    bazel run //packages/be_water/scripts:audit_data                 # verify sign-off
    bazel run //packages/be_water/scripts:audit_data -- --duplicates # merge dupes
    bazel run //packages/be_water/scripts:audit_data -- --suspicious # fix bad values
    bazel run //packages/be_water/scripts:audit_data -- --drift       # dataset vs live

Sign-off freezes a ficha as verified (label photo + ≥1 label-confirmed value);
non-label values keep their "fabricante" / "a mano" provenance. Every write is
behind a confirmation."""

import argparse
import os
import webbrowser

os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

from packages.be_water.web import data_audit, repository  # noqa: E402
from packages.be_water.web.domain import (  # noqa: E402
    MINERAL_FIELDS,
    MINERAL_LABELS,
    SOURCE_LABEL,
    SOURCE_MANUAL,
    SOURCE_MANUFACTURER,
)

_SOURCES = {"l": SOURCE_LABEL, "f": SOURCE_MANUFACTURER, "m": SOURCE_MANUAL}


def _prompt(text: str) -> str:
    try:
        return input(text).strip()
    except EOFError:
        return "q"


# --- sign-off ---------------------------------------------------------------


def _fields_summary(water) -> str:
    label = ", ".join(MINERAL_LABELS.get(f, f) for f in water.verified_fields)
    other = [f for f in water.minerals if f not in water.verified_fields]
    other_str = ", ".join(MINERAL_LABELS.get(f, f) for f in other) or "—"
    return f"    etiqueta: {label}\n    resto (fabricante/a mano): {other_str}"


def sign_off(catalog, open_photos: bool) -> None:
    todo = [w for w in catalog if data_audit.verifiable(w)]
    verified = sum(w.verified for w in catalog)
    print(f"\n{len(catalog)} fichas · {verified} verificadas · {len(todo)} firmables\n")
    if not todo:
        print("Nada que firmar.\n")
        return
    signed = 0
    for i, water in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {water.id} — {water.name}")
        print(_fields_summary(water))
        print(f"    etiqueta: {water.label_photo_url}")
        if open_photos:
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


# --- duplicates -------------------------------------------------------------


def duplicates(catalog) -> None:
    groups = data_audit.find_duplicates(catalog)
    print(f"\n{len(groups)} grupos de posibles duplicados.\n")
    for group in groups:
        print("Posible duplicado:")
        for water in group:
            flags = "✓" if water.verified else " "
            print(
                f"  [{flags}] {water.id} — {water.name} · {water.spring or '—'} "
                f"· {len(water.minerals)} valores"
            )
        keep_id = group[0].id
        answer = _prompt(
            f"   ¿fusionar el resto en «{keep_id}»? [f]usionar / [s]altar / [q]salir? "
        ).lower()
        if answer == "q":
            break
        if answer == "f":
            for drop in group[1:]:
                data_audit.merge_waters(group[0], drop)
                print(f"   fusionada {drop.id} → {keep_id}")
            print()
        else:
            print("   saltado.\n")


# --- suspicious -------------------------------------------------------------


def _correct(water) -> None:
    field = _prompt("      campo a corregir (p.ej. tds, enter=nada): ").lower()
    if field not in MINERAL_FIELDS:
        if field:
            print(f"      campo desconocido: {field}")
        return
    raw = _prompt("      nuevo valor: ").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        print("      valor no numérico.")
        return
    src = _SOURCES.get(
        _prompt("      fuente [l]etiqueta/[f]abricante/[m]ano: ").lower()
    )
    if not src:
        print("      fuente no válida.")
        return
    data_audit.correct_field(water, field, value, src)
    print(f"      {field} = {value} ({src}).")


def suspicious(catalog) -> None:
    findings = data_audit.find_suspicious(catalog)
    print(f"\n{len(findings)} fichas con valores sospechosos.\n")
    for water, reasons in findings:
        print(f"{water.id} — {water.name}")
        for reason in reasons:
            print(f"    ⚠ {reason}")
        answer = _prompt("    ¿[c]orregir un campo / [s]altar / [q]salir? ").lower()
        if answer == "q":
            break
        if answer == "c":
            _correct(water)
        print()


def drift(catalog) -> None:
    """Read-only: where the in-repo dataset and the live catalog disagree.

    A `[etiqueta]` difference means seed_data.py is stale and should be
    updated in a PR — the fix belongs in the repo, not in Firestore, so this
    pass never writes."""
    findings = data_audit.dataset_drift(catalog)
    print(f"\n{len(findings)} fichas difieren del dataset del repo.\n")
    for water, differences in findings:
        print(f"{water.id} — {water.name}")
        for difference in differences:
            print(f"    ≠ {difference}")
        print()
    if findings:
        print("Actualiza packages/be_water/web/seed_data.py en una PR.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--duplicates", action="store_true", help="review dupes")
    mode.add_argument("--suspicious", action="store_true", help="review bad values")
    mode.add_argument("--drift", action="store_true", help="dataset vs live catalog")
    parser.add_argument("--no-open", action="store_true", help="don't open photos")
    args = parser.parse_args()

    catalog = repository.get_all_waters()
    if args.duplicates:
        duplicates(catalog)
    elif args.suspicious:
        suspicious(catalog)
    elif args.drift:
        drift(catalog)
    else:
        sign_off(catalog, open_photos=not args.no_open)


if __name__ == "__main__":
    main()
