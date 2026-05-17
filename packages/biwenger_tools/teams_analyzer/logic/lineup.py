"""Lineup optimization for /alinear command.

Given a squad of rows (with jp_player and position data), finds the formation
and 11-player assignment that maximises the total SF predict score.

For a high-level walkthrough of the algorithm (with the multi-position
example that motivated exhaustive backtracking), see the
"How `/alinear` picks the lineup" section of `../README.md`.
"""

from html import escape

from core.sdk.jp import get_predict_rate
from packages.biwenger_tools.teams_analyzer.player_formatting import SCORE_SF

# All supported formations as (label, def, mid, fwd). GK is always 1.
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

# Position IDs as Biwenger reports them.
GK, DEF, MID, FWD = 1, 2, 3, 4

# Biwenger refuses to set a captain whose market value is ≥ 3M.
_CAPTAIN_MAX_PRICE = 3_000_000


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def pick_lineup(squad_rows: list) -> dict | None:
    """Pick the best (formation, starters, reserves, captain) for the squad.

    Returns `None` if no valid lineup can be formed from the available
    players (e.g. nobody can play GK).

    Return shape::

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
        reserves = _pick_reserves(available, starter_ids)
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


def format_lineup_message(result: dict) -> str:
    """Returns an HTML Telegram message confirming the lineup."""
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

    filled = [(pos_name[pos], r) for pos, r in zip((GK, DEF, MID, FWD), reserves) if r]
    if filled:
        lines.append("\n<b>Suplentes:</b>")
        for label, r in filled:
            lines.append(f"  {label} {escape(r['name'])} (SF:{_sf(r)})")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers — tiny pure functions used throughout
# ---------------------------------------------------------------------------


def _sf(row: dict) -> int:
    """Predicted SF score for a player. 0 if JP has no prediction."""
    jp = row.get("jp_player")
    return get_predict_rate(jp, SCORE_SF) or 0


def _positions(row: dict) -> set:
    """All positions a player can cover — primary + any alts."""
    primary = row.get("position_id")
    alts = row.get("alt_positions") or []
    return {primary} | set(alts)


def _is_available(row: dict) -> bool:
    """Whether a player can be picked for the lineup.

    Excludes:
    - players with no JP data (we can't predict their SF),
    - injured or suspended (per JP status),
    - matches in `break` (their team has no game this matchday),
    - `playerInLineup is False` — JP has *explicitly* said the player is not
      in the official squad list. A `None` means "unknown yet", which is the
      normal state hours before kickoff and is treated as still available.
    """
    jp = row.get("jp_player")
    if jp is None:
        return False
    if jp.get("status") in ("injured", "suspended"):
        return False
    next_match = jp.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return False
    if next_match.get("playerInLineup") is False:
        return False
    return True


# ---------------------------------------------------------------------------
# Internal: starters assignment (exhaustive backtracking)
# ---------------------------------------------------------------------------


def _try_fill(players: list, slots: dict) -> list | None:
    """Pick the assignment of `players` to `slots` that maximises total SF.

    Exhaustive backtracking: for each open slot try every eligible candidate,
    recurse on the rest, and keep the assignment with the highest sum of SF.
    Returns `None` if no valid assignment exists.

    Why exhaustive: a previous version returned the first feasible solution,
    which was wrong for multi-position players. Example with formation 4-3-3
    (3 MID + 3 FWD), a FWD/MID player X with SF 400, three other FWDs
    (380/360/340) and three MIDs (350/320/280):

      X as FWD → FWDs sum 1140, MIDs sum 950 = 2090
      X as MID → FWDs sum 1080, MIDs sum 1070 = 2150  ← global optimum

    The "first feasible" heuristic picked X as FWD because that's its primary
    position; the exhaustive variant picks the assignment that maximises the
    11-player SF total. The outer `pick_lineup()` still iterates the 12
    formations and keeps the best of those.

    To prune the search a bit, we fill the most-constrained position first
    (fewest eligible players). This does not change correctness but cuts
    branches early.
    """
    open_slots = [(pos, cnt) for pos, cnt in slots.items() if cnt > 0]
    if not open_slots:
        return []

    def eligible_count(pos):
        return sum(1 for r in players if pos in _positions(r))

    pos_to_fill = min(open_slots, key=lambda pc: eligible_count(pc[0]))[0]
    new_slots = {**slots, pos_to_fill: slots[pos_to_fill] - 1}

    # Try every candidate that can play this slot. Higher SF first so good
    # partial assignments surface early; this is a hint, not a guarantee,
    # since we explore all of them anyway.
    candidates = sorted(
        (r for r in players if pos_to_fill in _positions(r)),
        key=_sf,
        reverse=True,
    )

    best: list | None = None
    best_sf = -1
    for player in candidates:
        remaining = [r for r in players if r["bw_id"] != player["bw_id"]]
        sub = _try_fill(remaining, new_slots)
        if sub is None:
            continue
        sub_sf = _sf(player) + sum(_sf(r) for r, _ in sub)
        if sub_sf > best_sf:
            best_sf = sub_sf
            best = [(player, pos_to_fill)] + sub

    return best


# ---------------------------------------------------------------------------
# Internal: reserves and captain
# ---------------------------------------------------------------------------


def _pick_reserves(available: list, starter_ids: set) -> list:
    """Pick up to 4 reserves in Biwenger's positional order: GK → DEF → MID → FWD.

    For each position slot we pick the highest-SF eligible bench player that
    has not already been picked for an earlier slot. If no candidate exists
    for a slot we leave a `None` there — Biwenger accepts a partial bench.
    """
    bench_pool = [r for r in available if r["bw_id"] not in starter_ids]
    used_ids: set = set()
    reserves: list = []
    for slot_pos in (GK, DEF, MID, FWD):
        candidates = sorted(
            (
                r
                for r in bench_pool
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
    return reserves


def _pick_captain(starters: list) -> dict:
    """Captain must have price strictly < 3M (Biwenger API hard limit).

    Among eligible players, pick the highest SF (all cheap players double
    their score as captain, so relative SF ranking is the ordering criterion).

    If price is 0 (unknown / not set in API), treat as unknown and exclude —
    a 0-price player could be any value according to the API.

    If no player has a known price < 3M, fall back to the cheapest player
    with a known price (price > 0) to minimise the risk of an API rejection.
    """
    known_cheap = [r for r in starters if 0 < r.get("price", 0) < _CAPTAIN_MAX_PRICE]
    if known_cheap:
        return max(known_cheap, key=_sf)

    # No player with a known cheap price — pick the cheapest non-zero-price player
    with_price = [r for r in starters if r.get("price", 0) > 0]
    if with_price:
        return min(with_price, key=lambda r: r.get("price", 0))

    # All prices unknown — fall back to best SF
    return max(starters, key=_sf)
