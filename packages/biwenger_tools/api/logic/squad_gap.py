"""Where a manager's league points come from, round by round: the SofaScore
base the projections rank by, against the league's bonuses for playing,
winning and keeping a clean sheet — and how much of the round its two best
players carried.

Pure. The caller hands over each round's applied lineup (`get_round_league`)
and each player's `real_points.personalizado` over that matchday. How to read
the output: `docs/technical/backend/projection-ledger.md`, "Where the gap comes
from".
"""

from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID

# Biwenger's bench: one reserve per line, in this order. A starter who does
# not play is replaced by the reserve of his line, if that reserve played.
RESERVE_LINES = (GK, DEF, MID, FWD)

# What a clean sheet adds by position in this league (`personalizado`).
CLEAN_SHEET_BONUS = {GK: 2, DEF: 1}

PARTS = ("base", "play", "result", "clean", "other")


def counted(lineup: dict, played: set, position_of: dict) -> list:
    """The players whose points the round counts: each starter who played, or
    in his place the reserve of his line."""
    reserves = list(lineup.get("reserves") or [])
    out, used = [], set()
    for player_id in lineup.get("players") or []:
        if not player_id:
            continue
        if player_id in played:
            out.append(player_id)
            continue
        line = position_of.get(player_id)
        slot = RESERVE_LINES.index(line) if line in RESERVE_LINES else None
        sub = reserves[slot] if slot is not None and slot < len(reserves) else None
        if sub and sub in played and sub not in used:
            out.append(sub)
            used.add(sub)
    return out


def _parts(stats: dict, position) -> dict:
    base = stats.get("sofascore_real") or 0
    play = stats.get("long_games") or 0
    result = (stats.get("wins") or 0) - (stats.get("losses") or 0)
    clean = (stats.get("clean_sheets") or 0) * CLEAN_SHEET_BONUS.get(position, 0)
    points = stats.get("points") or 0
    return {
        "base": base,
        "play": play,
        "result": result,
        "clean": clean,
        "other": points - base - play - result - clean,
    }


def manager_round(lineup: dict, stats: dict, position_of: dict) -> dict:
    """One manager's round: `points` split into `PARTS`, the `wins` and
    `losses` of the players who counted, and `top_two`, the points of the two
    best of them. The captain counts twice, bonuses included."""
    played = {i for i, s in stats.items() if s.get("games")}
    ids = counted(lineup, played, position_of)
    captain = (lineup.get("captain") or {}).get("id")
    weight = {i: 2 if i == captain else 1 for i in ids}
    row = dict.fromkeys(("points", *PARTS, "wins", "losses"), 0)
    contributions = []
    for player_id in ids:
        s, w = stats[player_id], weight[player_id]
        parts = _parts(s, position_of.get(player_id))
        for key in PARTS:
            row[key] += w * parts[key]
        row["points"] += w * (s.get("points") or 0)
        row["wins"] += s.get("wins") or 0
        row["losses"] += s.get("losses") or 0
        contributions.append(w * (s.get("points") or 0))
    row["top_two"] = sum(sorted(contributions, reverse=True)[:2])
    return row


def summarize(rows_by_manager: dict) -> list:
    """Per manager, every round added up, most points first."""
    out = []
    for manager, rows in rows_by_manager.items():
        total = {
            k: sum(r[k] for r in rows)
            for k in ("points", *PARTS, "wins", "losses", "top_two")
        }
        out.append(
            {
                "manager": manager,
                "rounds": len(rows),
                **total,
                "bonus": total["points"] - total["base"],
                "top_two_share": total["top_two"] / total["points"]
                if total["points"]
                else 0.0,
            }
        )
    return sorted(out, key=lambda s: -s["points"] / max(s["rounds"], 1))
