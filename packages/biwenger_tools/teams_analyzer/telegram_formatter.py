"""Shared formatting helpers (status, position, play status) used by image_formatter."""

from core.sdk.jp import get_predict_rate

POSITION_SHORT = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL"}
SCORE_SF = 2


def _short_pos(pos_id) -> str:
    return POSITION_SHORT.get(pos_id, "?")


def _status_emoji(jp_player: dict | None) -> str:
    """Traffic-light status for a player.

    🔴 injured / suspended / no match / not in lineup / SF < 100
    🟡 100 ≤ SF < 300
    🟢 SF ≥ 300
    ⚪ no JP data
    """
    if jp_player is None:
        return "⚪"
    if jp_player.get("status") in ("injured", "suspended"):
        return "🔴"
    next_match = jp_player.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return "🔴"
    if next_match.get("playerInLineup") is False:
        return "🔴"
    sf = get_predict_rate(jp_player, SCORE_SF)
    if sf is None:
        return "🔴"
    if sf >= 300:
        return "🟢"
    if sf >= 100:
        return "🟡"
    return "🔴"


def _juega_str(jp_player: dict | None) -> str:
    if jp_player is None:
        return "sin datos"
    status = jp_player.get("status", "ok")
    if status == "injured":
        return "lesionado"
    if status == "suspended":
        return "sancionado"
    if status == "doubt":
        return "duda"
    next_match = jp_player.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return "sin partido"
    if next_match.get("playerInLineup") is False:
        return "no convocado"
    venue = "casa" if next_match.get("isLocal") else "fuera"
    return venue


def _sort_key_sf_desc(row: dict):
    """Sort key: players with SF first, then by SF descending."""
    jp = row.get("jp_player")
    sf = get_predict_rate(jp, SCORE_SF) if jp else None
    return (0 if sf is None else 1, sf or 0)


def _count_status(rows: list[dict]) -> tuple[int, int, int, int]:
    """Returns (green, yellow, red, white) counts."""
    g = y = r = w = 0
    for row in rows:
        e = _status_emoji(row.get("jp_player"))
        if e == "🟢":
            g += 1
        elif e == "🟡":
            y += 1
        elif e == "🔴":
            r += 1
        else:
            w += 1
    return g, y, r, w
