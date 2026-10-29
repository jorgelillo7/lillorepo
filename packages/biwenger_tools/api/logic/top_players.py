"""The five best players of every squad, for `/top`. Pure: no I/O.

Rows go to the shared table image, grouped manager by manager, with the
columns a manager weighs before a clausulazo: whose he is, his club, and the
clause — `Clausulable` says whether it can be paid today.
"""

from packages.biwenger_tools.api.player_formatting import shown_score

TOP_N = 5
EXTRA_COLS = ["Mánager", "Equipo", "Clausulable", "Cláusula"]


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
