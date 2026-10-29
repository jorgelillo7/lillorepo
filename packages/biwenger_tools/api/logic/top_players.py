"""The five best players of every squad, for `/top`. Pure: no I/O.

Rows go to the shared table image, one block per manager under a header row
with his name, with the columns a manager weighs before a clausulazo: the
club and the clause — `Clausulable` says whether it can be paid today.
"""

import time

from packages.biwenger_tools.api.player_formatting import shown_score

TOP_N = 5
EXTRA_COLS = ["Equipo", "Clausulable", "Cláusula"]
# Who plays is already the first column's marker; the word is room the club
# and the clause need more.
HIDDEN_COLS = ("Juega",)
# Each manager's block opens with a header row naming him (image `group_by`).
GROUP_KEY = "Mánager"


def best(rows: list[dict], n: int = TOP_N) -> list[dict]:
    """The `n` rows with the highest shown projection; unprojected rows last."""
    return sorted(rows, key=lambda r: shown_score(r) or 0, reverse=True)[:n]


def rows_for_image(blocks: list[tuple[str, list[dict]]], teams: dict) -> list[dict]:
    """Every manager's best, in manager order, each row labelled with its
    manager and club for the image's extra columns."""
    return [
        {**row, "Mánager": manager, "Equipo": teams.get(row.get("team_id")) or "—"}
        for manager, rows in blocks
        for row in rows
    ]


def locked(row: dict) -> bool:
    """Still under clause protection: drawn dim, since nobody can pay it yet."""
    until = row.get("clause_locked_until")
    return until is not None and until > time.time()
