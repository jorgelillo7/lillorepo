#!/usr/bin/env python3
"""Read the analysis date off each stored label photo (ADC + Gemini key).

`analysis_date` shipped after most fichas were created, so existing entries
carry none. The date is only on the bottle, and the only bottles this project
still has are the label photos in GCS — so the backfill re-reads those:

    bazel run //packages/be_water/scripts:backfill_analysis_date              # dry run
    bazel run //packages/be_water/scripts:backfill_analysis_date -- --write   # write

Reach is bounded by what was photographed: fichas without a label photo, and
those that already have a date, are skipped. Labels are not required to print
the date at all, so "no encontrada" is a legitimate outcome, not a failure.

The batch is paced: a dozen back-to-back OCR calls trip the Gemini free tier
(429/503) and most fichas come back unread. Use --only to check one cheaply."""

import argparse
import os
import time

import requests

os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

from core.sdk.gemini import GeminiError  # noqa: E402
from packages.be_water.web import label_ocr, repository, submission  # noqa: E402


def _prompt(text: str) -> str:
    try:
        return input(text).strip()
    except EOFError:
        return "q"


def _label_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def _read_label(url: str, attempts: int, delay: float) -> dict:
    """OCR one label, backing off on Gemini's transient overload responses.

    The SDK retries once, which is right for the web flow (a human is waiting)
    and far too little for a batch: the free tier throttles after a handful of
    images. Raises the last error when it never gets through."""
    for attempt in range(1, attempts + 1):
        try:
            return label_ocr.extract_label(_label_bytes(url))
        except GeminiError as exc:
            if exc.status_code not in (429, 503) or attempt == attempts:
                raise
            wait = delay * 2 ** (attempt - 1)
            print(f"    · Gemini {exc.status_code}, reintento en {wait:.0f}s")
            time.sleep(wait)
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="save, asking first")
    parser.add_argument("--only", help="a single water id")
    parser.add_argument(
        "--delay", type=float, default=6.0, help="seconds between labels (default 6)"
    )
    parser.add_argument(
        "--attempts", type=int, default=4, help="tries per label (default 4)"
    )
    args = parser.parse_args()

    catalog = repository.get_all_waters()
    todo = [w for w in catalog if w.label_photo_url and not w.analysis_date]
    if args.only:
        todo = [w for w in todo if w.id == args.only]
    skipped = len(catalog) - len(todo)
    print(
        f"\n{len(catalog)} fichas · {len(todo)} con etiqueta y sin fecha "
        f"· {skipped} sin foto de etiqueta o ya fechadas\n"
    )

    for i, water in enumerate(todo, 1):
        if i > 1:
            time.sleep(args.delay)
        print(f"[{i}/{len(todo)}] {water.id} — {water.name}")
        try:
            extracted = _read_label(water.label_photo_url, args.attempts, args.delay)
        except (GeminiError, requests.RequestException) as exc:
            print(f"    ✗ no se pudo leer: {str(exc)[:120]}\n")
            continue
        date = submission.normalize_analysis_date(extracted.get("analysis_date"))
        if not date:
            print("    — la etiqueta no imprime fecha de análisis\n")
            continue
        print(f"    → {date}")
        if not args.write:
            print()
            continue
        answer = _prompt("    ¿[g]uardar / [s]altar / [q]salir? ").lower()
        if answer == "q":
            break
        if answer != "g":
            print()
            continue
        water.analysis_date = date
        repository.save_water(water)
        print("    ✓ guardada.\n")

    if not args.write:
        print("Dry run — repite con --write para guardar.\n")


if __name__ == "__main__":
    main()
