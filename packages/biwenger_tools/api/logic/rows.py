"""Row builders shared by every endpoint that renders a squad or market view.

Pure functions over `(biwenger_player_dict, jp_index)`. Kept free of side
effects so the same row dict feeds the PNG image builder, the JSON
recommendations endpoint, etc.
"""

import math
import time

from packages.biwenger_tools.api.logic.player_matching import find_player_match

SECONDS_PER_DAY = 86400


def clausulable_str(locked_until) -> str:
    """Render the `Clausulable` table cell from a `clauseLockedUntil` epoch."""
    if locked_until is None:
        return "Sí"
    remaining_secs = locked_until - time.time()
    if remaining_secs <= 0:
        return "Sí"
    # floor: 11.28 days → 11 (matches "día 21" when today is the 10th)
    # max(1, ...) so sub-day locks still show "No (1d)" instead of "Sí"
    remaining = max(1, math.floor(remaining_secs / SECONDS_PER_DAY))
    return f"No ({remaining}d)"


def clause_str(clause) -> str:
    if not clause:
        return "-"
    m = int(clause) / 1_000_000
    return f"{m:.1f}M" if int(clause) % 1_000_000 else f"{int(m)}M"


def build_row(biwenger_player: dict, jp_index: dict) -> dict:
    name = biwenger_player.get("name", "N/A")
    return {
        "bw_id": biwenger_player.get("id"),
        "name": name,
        "position_id": biwenger_player.get("position"),
        "alt_positions": biwenger_player.get("altPositions") or [],
        "price": biwenger_player.get("price", 0),
        "jp_player": find_player_match(name, jp_index),
    }


def build_market_rows(
    market_players: list, biwenger_players: dict, jp_index: dict
) -> list:
    rows = []
    for sale in market_players:
        if sale.get("user") is not None:
            continue
        bw_player = biwenger_players.get(sale.get("player", {}).get("id"))
        if not bw_player:
            continue
        rows.append(build_row(bw_player, jp_index))
    return rows


def build_squad_rows(
    squad: list,
    biwenger_players: dict,
    jp_index: dict,
    include_clause: bool = False,
) -> list:
    rows = []
    for player_data in squad:
        bw_player = biwenger_players.get(player_data.get("id"))
        if not bw_player:
            continue
        row = build_row(bw_player, jp_index)
        # `row["price"]` MUST stay as the cf.biwenger.com base price (not
        # `owner.price`). Biwenger's server validates the 3M captain MV cap
        # against cf-base; using owner.price (per-league live MV) silently
        # passes the client check then gets rejected with
        # "Captain over max MV". The maxBid math in `core/sdk/biwenger.py`
        # also reads cf-base. `owner.price` is only used for the clause
        # block below.
        if include_clause:
            owner = player_data.get("owner") or {}
            locked_until = owner.get("clauseLockedUntil")
            clause_raw = owner.get("clause")
            # Formatted strings — consumed by the PNG renderer.
            row["Clausulable"] = clausulable_str(locked_until)
            row["Cláusula"] = clause_str(clause_raw)
            # Raw values — consumed by the JSON recommendations endpoint.
            # Don't show up in PNG output (only "Clausulable"/"Cláusula" are
            # rendered as extra columns there).
            row["clause_value"] = int(clause_raw) if clause_raw else 0
            row["clausulable_now"] = locked_until is None or (
                (locked_until - time.time()) <= 0
            )
        rows.append(row)
    return rows
