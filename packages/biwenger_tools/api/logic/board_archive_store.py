"""Read side of the board archive the scraper keeps.

`board_archive/{season}/entries` holds every money entry of the season, raw,
as JSON under `entry` — written append-only by the scraper job. This module is
the api's only route to it; the merge with the live board is pure
(`league_cash.with_archive`).
"""

import json

from core.sdk import firestore as fs


def load(season: str) -> list[dict]:
    """Every archived board entry of `season`, as Biwenger returned it."""
    return [
        json.loads(data["entry"])
        for _, data in fs.list_documents(f"board_archive/{season}/entries")
    ]
