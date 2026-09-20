"""A daily snapshot of the Oráculo blend against Jornada Perfecta alone.

`ORACULO_W`, `ORACULO_MAX_MOVE` and `ORACULO_MIN_COVERAGE` (`api/config.py`)
were set by hand, with nothing measuring whether the blend they define
actually beats Jornada Perfecta alone. This module builds the record that
can answer that: for the round the morning's lineup pick actually lands on,
the eleven the blend fields and the eleven Jornada Perfecta alone would
field, side by side.

Pure functions only; `projection_ledger_store.py` owns the one collection
this needs, so a Firestore failure can never reach here.
"""

from datetime import datetime

from core.sdk.jp import get_predict_rate
from packages.biwenger_tools.api.logic import round_context
from packages.biwenger_tools.api.logic.lineup import solve_lineup
from packages.biwenger_tools.api.player_formatting import SCORE_SF


def target_round(round_data: dict, now: datetime) -> int | None:
    """The round id this morning's lineup pick actually lands on, or `None`.

    Biwenger registers the lineup for whichever round has not kicked off yet
    (`openspec/project.md`, "the lineup is registered before the matchday
    begins"). Under *jornada única* the current round is usually already
    under way by 09:00, so the target is normally `round_data["next"]`, not
    `round_data["id"]` — the column a naive read would grab.

    Returns `None` rather than guessing when neither kickoff can be
    confirmed: the caller must never write once a match may already have
    started, and an unconfirmed kickoff is treated the same as a confirmed
    one in the past.
    """
    if not isinstance(round_data, dict):
        return None

    current_id = round_data.get("id")
    current_kickoff = round_context.first_kickoff(round_data.get("games"))
    if current_id is not None and current_kickoff is not None and now < current_kickoff:
        return current_id

    nxt = round_data.get("next") or {}
    next_id = nxt.get("id")
    next_kickoff = round_context.first_kickoff(nxt.get("games"))
    if next_id is not None and next_kickoff is not None and now < next_kickoff:
        return next_id

    return None


def _jp_sf(row: dict) -> int | None:
    return get_predict_rate(row.get("jp_player"), SCORE_SF)


def _strip_blend(rows: list) -> list:
    """`rows` with the blend switched off, so `solve_lineup` falls back to
    `jp_sf` for every player (`shown_score`'s own contract) — the eleven
    Jornada Perfecta alone would field."""
    return [{**row, "custom_prediction": None} for row in rows]


def _xi_summary(result: dict | None) -> dict | None:
    if result is None:
        return None
    captain = result.get("captain")
    return {
        "formation": result["formation"],
        "player_ids": [row["bw_id"] for row, _ in result["starters"]],
        "captain_id": captain["bw_id"] if captain else None,
    }


def build_snapshot(
    round_id: int, round_name: str | None, season: str, rows: list, now: datetime
) -> dict:
    """The document `projection_ledger_store.write` persists.

    Runs `solve_lineup` twice — once on `rows` as built, once with the blend
    stripped — never through `pick_lineup`: this is exactly the counterfactual
    `xi_snapshot`'s own docstring warns must not reach `provider_watch`'s
    audit trail, and running it twice would additionally double whichever
    call did.
    """
    blended = solve_lineup(rows)
    jp_only = solve_lineup(_strip_blend(rows))
    blended_xi = _xi_summary(blended)
    jp_only_xi = _xi_summary(jp_only)

    diff = {"only_blended": [], "only_jp": []}
    differs = False
    if blended_xi is not None and jp_only_xi is not None:
        blended_ids = set(blended_xi["player_ids"])
        jp_ids = set(jp_only_xi["player_ids"])
        diff = {
            "only_blended": sorted(blended_ids - jp_ids),
            "only_jp": sorted(jp_ids - blended_ids),
        }
        differs = bool(diff["only_blended"] or diff["only_jp"])

    return {
        "season": season,
        "round_id": round_id,
        "round_name": round_name,
        "captured_at": now.isoformat(),
        "has_projection": True,
        "players": [
            {
                "bw_id": row.get("bw_id"),
                "name": row.get("name"),
                "position_id": row.get("position_id"),
                "jp_sf": _jp_sf(row),
                "oraculo_points": row.get("oraculo_points"),
                "oraculo_matched": bool(row.get("oraculo_matched")),
                "custom_prediction": row.get("custom_prediction"),
            }
            for row in rows
        ],
        "blended_xi": blended_xi,
        "jp_only_xi": jp_only_xi,
        "xi_differs": differs,
        "xi_diff": diff,
    }


def xi_real_points(player_ids: list, captain_id: int | None, real_points: dict) -> int:
    """The eleven's actual score: each player's real points, captain doubled.

    A player absent from `real_points` counts as `0`, not Biwenger's `-4`
    "unoccupied position" penalty — every slot here is filled by a named
    player, one who this time drew no `rawStats` events for the round (did
    not play, or no report reached us), which the league's own scoring
    already treats as a plain zero rather than an empty seat.
    """
    total = 0
    for player_id in player_ids:
        points = real_points.get(player_id, 0)
        total += points * 2 if player_id == captain_id else points
    return total


def extract_applied_lineup(round_league_data: dict, user_id: int) -> dict | None:
    """This manager's actually-fielded eleven for a round, from
    `BiwengerClient.get_round_league()`'s payload, or `None` if the round's
    standings do not carry him.

    `player_ids` drops the `null` bench slots `lineup.players` sends for an
    unfilled position — Biwenger's own -4-per-empty-slot penalty already
    priced those into `points`, and there is no id left to score again here.
    """
    standings = (round_league_data.get("league") or {}).get("standings") or []
    for entry in standings:
        if entry.get("id") != user_id:
            continue
        lineup = entry.get("lineup") or {}
        captain = lineup.get("captain") or {}
        return {
            "formation": lineup.get("type"),
            "player_ids": [pid for pid in (lineup.get("players") or []) if pid],
            "captain_id": captain.get("id"),
            "points": entry.get("points"),
        }
    return None


# How many rounds where the two elevens actually differed before the summary
# will commit to a direction. A sign test over fewer than this cannot tell a
# consistent blend from a run of luck, and a number printed early is a number
# somebody acts on — the point of measuring was to stop deciding by feel, so
# a premature verdict defeats the exercise rather than advancing it.
MIN_ROUNDS_FOR_VERDICT = 10


def grade(documents: list) -> dict:
    """What the stored rounds add up to, and whether that is yet anything.

    Only rounds that carry a projection, have their outcome, **and** whose two
    elevens differed are evidence. A round both versions would have played
    identically contributes a zero that is not a measurement: averaging it in
    moves the answer towards "no effect" by arithmetic rather than by
    observation, and most rounds are that round.
    """
    compared = []
    for document in documents or []:
        if not document.get("has_projection"):
            continue
        if not document.get("xi_differs"):
            continue
        actual = document.get("actual") or {}
        blended = actual.get("blended_total")
        jp_only = actual.get("jp_only_total")
        if blended is None or jp_only is None:
            continue
        compared.append(
            {
                "round_id": document.get("round_id"),
                "blended": blended,
                "jp_only": jp_only,
                "delta": blended - jp_only,
            }
        )

    deltas = [row["delta"] for row in compared]
    won = sum(1 for delta in deltas if delta > 0)
    lost = sum(1 for delta in deltas if delta < 0)
    enough = len(compared) >= MIN_ROUNDS_FOR_VERDICT
    return {
        "rounds_stored": len(documents or []),
        "rounds_compared": len(compared),
        "rounds_needed": max(0, MIN_ROUNDS_FOR_VERDICT - len(compared)),
        "rows": compared,
        "deltas": deltas,
        "blend_won": won,
        "blend_lost": lost,
        "total_delta": sum(deltas),
        "verdict": (f"{won} of {len(compared)} to the blend" if enough else None),
    }
