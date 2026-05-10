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

_CAPTAIN_MAX_PRICE = 3_000_000


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

    For multi-position players, prefer assigning to their primary (most
    defensive) position: candidates whose position_id matches the slot being
    filled come before candidates using an alt_position for that slot.
    """
    open_slots = [(pos, cnt) for pos, cnt in slots.items() if cnt > 0]
    if not open_slots:
        return []

    def eligible_count(pos):
        return sum(1 for r in players if pos in _positions(r))

    pos_to_fill = min(open_slots, key=lambda pc: eligible_count(pc[0]))[0]
    new_slots = {**slots, pos_to_fill: slots[pos_to_fill] - 1}

    # Prefer players whose PRIMARY position matches the slot (most defensive use)
    candidates = sorted(
        (r for r in players if pos_to_fill in _positions(r)),
        key=lambda r: (r.get("position_id") != pos_to_fill, -_sf(r)),
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
        "reserves": [row | None, ...],       # 4 entries (None = empty slot)
        "captain": row,
        "total_sf": int,
    }
    """
    available = [r for r in squad_rows if _is_available(r)]
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
        bench_pool = [r for r in available if r["bw_id"] not in starter_ids]
        # Biwenger reserve slots are positional: slot1=GK, slot2=DEF, slot3=MID, slot4=FWD
        used_ids: set = set()
        reserves = []
        for slot_pos in (GK, DEF, MID, FWD):
            candidates = sorted(
                (
                    r for r in bench_pool
                    if r["bw_id"] not in used_ids and slot_pos in _positions(r)
                ),
                key=_sf,
                reverse=True,
            )
            if candidates:
                reserves.append(candidates[0])
                used_ids.add(candidates[0]["bw_id"])
            else:
                reserves.append(None)

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
    """Captain must have price strictly < 3M (Biwenger API hard limit).

    Among eligible players, pick the highest SF (all cheap players double
    their score as captain, so relative SF ranking is the ordering criterion).

    If price is 0 (unknown / not set in API), treat as unknown and exclude —
    a 0-price player could be any value according to the API.

    If no player has a known price < 3M, fall back to the cheapest player
    with a known price (price > 0) to minimise the risk of an API rejection.
    """
    known_cheap = [
        r for r in starters if 0 < r.get("price", 0) < _CAPTAIN_MAX_PRICE
    ]
    if known_cheap:
        return max(known_cheap, key=_sf)

    # No player with a known cheap price — pick the cheapest non-zero-price player
    with_price = [r for r in starters if r.get("price", 0) > 0]
    if with_price:
        return min(with_price, key=lambda r: r.get("price", 0))

    # All prices unknown — fall back to best SF
    return max(starters, key=_sf)


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

    slot_label = {GK: "POR", DEF: "DEF", MID: "MED", FWD: "DEL"}
    filled = [(slot_label[pos], r) for pos, r in zip((GK, DEF, MID, FWD), reserves) if r]
    if filled:
        lines.append("\n<b>Suplentes:</b>")
        for label, r in filled:
            lines.append(f"  {label} {escape(r['name'])} (SF:{_sf(r)})")

    return "\n".join(lines)
