#!/usr/bin/env python3
"""Diagnostic: list categoria counts for a season and flag drift between
``categorize_title(titulo)`` and the ``categoria`` Firestore actually stored.

Usage::

    python3 scripts/biwenger_check_categorias.py [season]

``season`` defaults to ``25-26``. Read-only — touches nothing in Firestore.
Pair with ``biwenger_recategorise.py`` to fix the drift it surfaces.
"""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.sdk.firestore import get_client  # noqa: E402
from packages.biwenger_tools.scraper_job.logic.processing import (  # noqa: E402
    categorize_title,
)


def main() -> None:
    season = sys.argv[1] if len(sys.argv) > 1 else "25-26"
    client = get_client()
    coll = client.collection(f"comunicados/{season}/messages")

    counts: dict[str, int] = defaultdict(int)
    drift: list[tuple[str, str, str, str]] = []
    for snap in coll.stream():
        data = snap.to_dict() or {}
        stored = data.get("categoria") or "(missing)"
        counts[stored] += 1
        expected = categorize_title(data.get("titulo", ""))
        if expected != stored:
            drift.append(
                (
                    str(data.get("fecha", ""))[:19],
                    data.get("autor", ""),
                    data.get("titulo", ""),
                    f"{stored} → {expected}",
                )
            )

    print(f"\n=== Counts for {season} ===")
    for cat in sorted(counts):
        print(f"  {cat:15s}  {counts[cat]}")

    print(f"\n=== Drift ({len(drift)} docs whose stored categoria != expected) ===")
    if not drift:
        print("  (clean)")
        return
    for fecha, autor, titulo, change in sorted(drift):
        print(f"  {fecha:20s}  {autor:30s}  {titulo!r:40s}  {change}")
    print("\nRun scripts/biwenger_recategorise.py " f"{season} --apply  to fix these.")


if __name__ == "__main__":
    main()
