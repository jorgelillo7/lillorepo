"""Player formatting helpers (status, position, play status) shared across renderers."""

from core.sdk.jp import get_predict_rate

POSITION_SHORT = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL"}

# Score type 2 = "SF" (SofaScore-based Automanager rate).
# Used wherever we read predictions from JP.
SCORE_SF = 2

# Traffic-light thresholds based on the predicted SF score.
# Tuned by hand against past matchdays; reused by status_emoji().
SF_GREEN_THRESHOLD = 300
SF_YELLOW_THRESHOLD = 100


def short_position(position_id) -> str:
    return POSITION_SHORT.get(position_id, "?")


def status_emoji(jp_player: dict | None) -> str:
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
    if sf >= SF_GREEN_THRESHOLD:
        return "🟢"
    if sf >= SF_YELLOW_THRESHOLD:
        return "🟡"
    return "🔴"


def play_status_label(jp_player: dict | None) -> str:
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
    return "casa" if next_match.get("isLocal") else "fuera"


def sort_key_sf_desc(row: dict):
    """Sort key: players with SF first, then by SF descending."""
    jp = row.get("jp_player")
    sf = get_predict_rate(jp, SCORE_SF) if jp else None
    return (0 if sf is None else 1, sf or 0)


def count_status_buckets(rows: list[dict]) -> tuple[int, int, int, int]:
    """Returns (green, yellow, red, white) counts."""
    green = yellow = red = white = 0
    for row in rows:
        emoji = status_emoji(row.get("jp_player"))
        if emoji == "🟢":
            green += 1
        elif emoji == "🟡":
            yellow += 1
        elif emoji == "🔴":
            red += 1
        else:
            white += 1
    return green, yellow, red, white
