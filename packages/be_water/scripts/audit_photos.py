#!/usr/bin/env python3
"""Interactive photo audit for the be_water catalog.

Two passes over the same local JSON map (resumable, git-ignored):

    # 1. Diagnose — count fichas with photos, review each, record a verdict.
    bazel run //packages/be_water/scripts:audit_photos

    # 2. Fix — walk the flagged verdicts and repair (studio / re-upload / delete).
    bazel run //packages/be_water/scripts:audit_photos -- --fix

Runs locally against the be-water-app project via ADC
(`gcloud auth application-default login`). The audit pass is read-only; --fix
mutates GCS + Firestore and asks before every write. Studio regeneration needs
GEMINI_API_KEY (from packages/be_water/web/.env)."""

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

# be_water lives in its own GCP project; set this before the Firestore client
# is created (importing config would also do it, but the script doesn't need
# the Flask app config).
os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

from packages.be_water.web import photo_audit, repository  # noqa: E402

_VERDICT_LABEL = {
    photo_audit.OK: "OK",
    photo_audit.MAIN_NOT_STUDIO: "foto principal sin studio",
    photo_audit.WRONG_LABEL: "etiqueta de composición incorrecta",
    photo_audit.BOTH: "ambas mal",
    photo_audit.NO_PHOTO: "sin foto",
}
# Single-key answers in the audit prompt.
_KEYS = {
    "o": photo_audit.OK,
    "m": photo_audit.MAIN_NOT_STUDIO,
    "l": photo_audit.WRONG_LABEL,
    "b": photo_audit.BOTH,
}


def _map_path(arg: str | None) -> Path:
    """Resolve the JSON map against the dir the user ran bazel from, so writes
    land in the repo rather than the ephemeral runfiles tree."""
    if arg:
        return Path(arg).expanduser()
    root = os.environ.get("BUILD_WORKING_DIRECTORY", os.getcwd())
    return Path(root) / "photo_audit.json"


def _load_map(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_map(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _open(urls, enabled: bool) -> None:
    if not enabled:
        return
    for url in urls:
        if url:
            webbrowser.open(url)


def _prompt(text: str) -> str:
    try:
        return input(text).strip()
    except EOFError:
        return "q"


def audit(reviews: dict, path: Path, open_photos: bool, review_all: bool) -> None:
    statuses = photo_audit.scan_catalog()
    with_main = sum(s.has_main for s in statuses)
    with_label = sum(s.has_label for s in statuses)
    not_studio = sum(s.studio_ok is False for s in statuses)
    print(
        f"\n{len(statuses)} fichas con foto  ·  {with_main} con principal "
        f"({not_studio} sin studio detectado)  ·  {with_label} con etiqueta\n"
    )

    todo = [s for s in statuses if review_all or s.water_id not in reviews]
    if not todo:
        print("Todo revisado. Usa --all para re-revisar o --fix para arreglar.\n")
        return
    print(f"Pendientes de revisar: {len(todo)}. (s = saltar, q = salir)\n")

    for i, status in enumerate(todo, 1):
        suggested = photo_audit.suggest_verdict(status)
        studio = {True: "✓ studio", False: "✗ NO studio", None: "?"}[status.studio_ok]
        print(f"[{i}/{len(todo)}] {status.water_id} — {status.name}")
        print(f"    principal: {status.main_url or '—'}  [{studio}]")
        print(f"    etiqueta : {status.label_url or '—'}")
        print(f"    sugerido : {_VERDICT_LABEL[suggested]}")
        _open([status.main_url, status.label_url], open_photos)

        answer = _prompt(
            "    ¿[o]k / principal sin studio [m] / etiqueta mal [l] / "
            "[b]ambas / [s]altar / [q]salir? "
        ).lower()
        if answer == "q":
            break
        if answer == "s":
            continue
        verdict = _KEYS.get(answer) or suggested  # empty → accept the suggestion
        reviews[status.water_id] = {"verdict": verdict, "name": status.name}
        _save_map(path, reviews)
        print(f"    → {_VERDICT_LABEL[verdict]}\n")

    counts: dict[str, int] = {}
    for entry in reviews.values():
        counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1
    print("\nResumen de veredictos:")
    for verdict, n in sorted(counts.items()):
        print(f"  {n:3d}  {_VERDICT_LABEL.get(verdict, verdict)}")
    worklist = [
        wid for wid, e in reviews.items() if e["verdict"] in photo_audit.FIXABLE
    ]
    print(f"\n{len(worklist)} para arreglar → corre con --fix.\n")


def _read_file_bytes(prompt: str) -> bytes | None:
    raw = _prompt(prompt)
    if not raw:
        return None
    file_path = Path(raw).expanduser()
    if not file_path.is_file():
        print(f"    No existe: {file_path}")
        return None
    return file_path.read_bytes()


def _fix_main(water) -> bool:
    print("    Foto principal:")
    choice = _prompt(
        "      [r] regenerar studio desde la actual / [f] subir nueva foto "
        "(ruta) / [enter] dejar: "
    ).lower()
    if choice == "r":
        url = photo_audit.rerun_studio(water)
        print(f"      studio regenerada → {url}")
        return True
    if choice == "f":
        data = _read_file_bytes("      ruta de la nueva foto principal: ")
        if data:
            url = photo_audit.set_main_photo(water, data, studioise=True)
            print(f"      subida y pasada por studio → {url}")
            return True
    return False


def _fix_label(water) -> bool:
    data = _read_file_bytes(
        "    Etiqueta de composición — ruta de la foto correcta (enter para dejar): "
    )
    if data:
        url = photo_audit.replace_label(water, data)
        print(f"      etiqueta reemplazada → {url}")
        return True
    return False


def fix(reviews: dict, path: Path) -> None:
    worklist = [
        (wid, e) for wid, e in reviews.items() if e["verdict"] in photo_audit.FIXABLE
    ]
    if not worklist:
        print("Nada marcado para arreglar. Corre la auditoría primero.\n")
        return
    print(f"\n{len(worklist)} fichas para arreglar. (q para salir)\n")

    for wid, entry in worklist:
        verdict = entry["verdict"]
        water = repository.get_water(wid)
        if water is None:
            print(f"  {wid}: ya no existe, salto.\n")
            continue
        print(f"── {wid} — {water.name}  [{_VERDICT_LABEL[verdict]}]")

        action = _prompt(
            "   [f]ix (foto/etiqueta) / [x] BORRAR ficha / [s]altar / [q]salir? "
        ).lower()
        if action == "q":
            break
        if action in ("", "s"):
            continue
        if action == "x":
            if _prompt(f"   escribe «{wid}» para confirmar el borrado: ") == wid:
                photo_audit.delete_water(water)
                del reviews[wid]
                _save_map(path, reviews)
                print("   ficha borrada.\n")
            else:
                print("   borrado cancelado.\n")
            continue

        fixed = False
        if verdict in (photo_audit.MAIN_NOT_STUDIO, photo_audit.BOTH):
            fixed = _fix_main(water) or fixed
        if verdict in (photo_audit.WRONG_LABEL, photo_audit.BOTH):
            fixed = _fix_label(water) or fixed
        if fixed:
            reviews[wid] = {"verdict": photo_audit.OK, "name": water.name}
            _save_map(path, reviews)
            print("   marcada OK.\n")
        else:
            print("   sin cambios.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="repair flagged fichas")
    parser.add_argument("--map", help="path to the JSON map (default: repo root)")
    parser.add_argument(
        "--all", action="store_true", help="re-review already-recorded fichas"
    )
    parser.add_argument(
        "--no-open", action="store_true", help="don't open photos in the browser"
    )
    args = parser.parse_args()

    path = _map_path(args.map)
    reviews = _load_map(path)
    print(f"Mapa: {path}")

    if args.fix:
        fix(reviews, path)
    else:
        audit(reviews, path, open_photos=not args.no_open, review_all=args.all)


if __name__ == "__main__":
    sys.exit(main())
