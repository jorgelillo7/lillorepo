"""Lineup optimization for /alinear command.

Given a squad of rows (with jp_player and position data), finds the formation
and 11-player assignment that maximises the total SF predict score.
"""

from core.sdk.jp import get_predict_rate

SCORE_SF = 2

# All supported formations as (label, def, mid, fwd)
FORMATIONS = [
    ("3-4-3", 3, 4, 3),
    ("3-5-2", 3, 5, 2),
    ("4-3-3", 4, 3, 3),
    ("4-4-2", 4, 4, 2),
    ("4-5-1", 4, 5, 1),
    ("5-3-2", 5, 3, 2),
    ("5-4-1", 5, 4, 1),
    ("3-6-1", 3, 6, 1),
    ("3-3-4", 3, 3, 4),
    ("4-2-4", 4, 2, 4),
    ("4-6-0", 4, 6, 0),
    ("5-2-3", 5, 2, 3),
]

# Position IDs: 1=GK, 2=DEF, 3=MID, 4=FWD
GK, DEF, MID, FWD = 1, 2, 3, 4


def _sf(row: dict) -> int:
    jp = row.get("jp_player")
    return get_predict_rate(jp, SCORE_SF) or 0


def _positions(row: dict) -> set:
    primary = row.get("position_id")
    alts = row.get("alt_positions") or []
    return {primary} | set(alts)


def _is_available(row: dict) -> bool:
    jp = row.get("jp_player")
    if jp is None:
        return False
    status = jp.get("status", "ok")
    if status in ("injured", "suspended"):
        return False
    return jp.get("nextMatch", {}).get("status") != "break"


def _try_fill(players: list, slots: dict) -> list | None:
    """Backtracking: fills `slots` {pos: count} from `players` sorted by SF desc.

    Returns a list of (player, assigned_pos) for the starters, or None if the
    formation cannot be filled with the given players.
    Assigns the most-constrained positions first (fewest eligible players).
    """
    # Find the next slot to fill — pick the position with fewest eligible players
    open_slots = [(pos, cnt) for pos, cnt in slots.items() if cnt > 0]
    if not open_slots:
        return []

    avail_ids = {r["bw_id"] for r in players}

    def eligible_count(pos):
        return sum(
            1 for r in players if r["bw_id"] in avail_ids and pos in _positions(r)
        )

    pos_to_fill = min(open_slots, key=lambda pc: eligible_count(pc[0]))[0]
    new_slots = {**slots, pos_to_fill: slots[pos_to_fill] - 1}

    # Try each player eligible for this position, best SF first
    candidates = sorted(
        (r for r in players if pos_to_fill in _positions(r)),
        key=_sf,
        reverse=True,
    )
    for player in candidates:
        remaining = [r for r in players if r["bw_id"] != player["bw_id"]]
        result = _try_fill(remaining, new_slots)
        if result is not None:
            return [(player, pos_to_fill)] + result

    return None


def pick_lineup(squad_rows: list) -> dict | None:
    """Returns the best lineup dict or None if no valid lineup can be formed.

    Return shape:
    {
        "formation": "4-5-1",
        "starters": [(row, pos_id), ...],   # 11 entries
        "reserves": [row, ...],              # up to 4, sorted SF desc
        "captain": row,
        "total_sf": int,
    }
    """
    available = [r for r in squad_rows if _is_available(r)]
    # Sort by SF desc — backtracking picks best candidates first
    available.sort(key=_sf, reverse=True)

    best: dict | None = None
    best_sf = -1

    for label, n_def, n_mid, n_fwd in FORMATIONS:
        slots = {GK: 1, DEF: n_def, MID: n_mid, FWD: n_fwd}
        assignment = _try_fill(available, slots)
        if assignment is None:
            continue

        total_sf = sum(_sf(r) for r, _ in assignment)
        if total_sf <= best_sf:
            continue

        starter_ids = {r["bw_id"] for r, _ in assignment}
        reserves = sorted(
            (r for r in available if r["bw_id"] not in starter_ids),
            key=_sf,
            reverse=True,
        )[:4]

        captain = _pick_captain([r for r, _ in assignment])

        best_sf = total_sf
        best = {
            "formation": label,
            "starters": assignment,
            "reserves": reserves,
            "captain": captain,
            "total_sf": total_sf,
        }

    return best


def _pick_captain(starters: list) -> dict:
    """Cheap players (< 3M) score double — pick highest SF among them.
    Fall back to global highest SF if none are cheap.
    """
    cheap = [r for r in starters if r.get("price", 0) < 3_000_000]
    pool = cheap if cheap else starters
    return max(pool, key=_sf)


def format_lineup_message(result: dict) -> str:
    """Returns an HTML Telegram message confirming the lineup."""
    from html import escape

    formation = result["formation"]
    starters = result["starters"]
    reserves = result["reserves"]
    captain = result["captain"]
    total_sf = result["total_sf"]

    pos_name = {GK: "POR", DEF: "DEF", MID: "MED", FWD: "DEL"}
    lines = [f"<b>✅ Alineación aplicada — {formation}</b> (SF total: {total_sf})\n"]

    for pos_id in (GK, DEF, MID, FWD):
        group = [(r, p) for r, p in starters if p == pos_id]
        group.sort(key=lambda rp: _sf(rp[0]), reverse=True)
        for row, _ in group:
            sf = _sf(row)
            cap = " ©" if row["bw_id"] == captain["bw_id"] else ""
            lines.append(f"{pos_name[pos_id]} {escape(row['name'])} (SF:{sf}){cap}")

    if reserves:
        lines.append("\n<b>Suplentes:</b>")
        for r in reserves:
            lines.append(f"  {escape(r['name'])} (SF:{_sf(r)})")

    return "\n".join(lines)
