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

from datetime import datetime, timedelta

from core.sdk.jp import get_predict_rate
from packages.biwenger_tools.api.logic import round_context
from packages.biwenger_tools.api.logic.lineup import solve_lineup
from packages.biwenger_tools.api.player_formatting import SCORE_SF


def target_round(round_data: dict, now: datetime) -> int | None:
    """The round id this morning's lineup pick actually lands on, or `None`.

    Biwenger registers the lineup for whichever round has not kicked off yet
    (`openspec/project.md`, "the lineup is registered before the matchday
    begins"). Under *jornada única* the current round is usually already
    under way by 07:15, so the target is normally `round_data["next"]`, not
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

    diff: dict[str, list] = {"only_blended": [], "only_jp": []}
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
                "oraculo_chance": row.get("oraculo_chance"),
                "oraculo_lists": list(row.get("oraculo_lists") or []),
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


def outcome_totals(document: dict) -> tuple[int, int] | None:
    """The real score of the blended eleven and of the Jornada-Perfecta-alone
    eleven for a stored round, or `None` when it cannot be known.

    `report.py --apply` stores the two totals; the morning digest stores
    per-player points and no totals, so they are scored here from those.
    Only when every player of both elevens has points, though: a player
    whose reports could not be read has none stored, and counting him as 0
    would invent a result.
    """
    actual = document.get("actual") or {}
    if (
        actual.get("blended_total") is not None
        and actual.get("jp_only_total") is not None
    ):
        return actual["blended_total"], actual["jp_only_total"]
    points = actual.get("player_points") or {}
    elevens = [document.get("blended_xi") or {}, document.get("jp_only_xi") or {}]
    ids = [pid for xi in elevens for pid in xi.get("player_ids") or []]
    if not ids or any(pid not in points for pid in ids):
        return None
    blended, jp_only = (
        xi_real_points(xi.get("player_ids") or [], xi.get("captain_id"), points)
        for xi in elevens
    )
    return blended, jp_only


def extract_league_points(round_league_data: dict) -> list[dict]:
    """Every manager's score for the round, from `get_round_league()`'s
    payload: `lineup.points`, the round's own score — the standing's `points`
    is the season total. A member who fielded nothing has no round score and
    is left out rather than counted as 0.
    """
    standings = (round_league_data.get("league") or {}).get("standings") or []
    out = []
    for entry in standings:
        points = (entry.get("lineup") or {}).get("points")
        if points is None:
            continue
        out.append({"id": entry.get("id"), "name": entry.get("name"), "points": points})
    return out


def league_ranking(document: dict) -> list[dict]:
    """Every squad's projected eleven against what it scored, for one round:
    `[{manager, projected, projected_rank, points, points_rank}]`, best
    projection first, or `[]` until the round has both halves.

    The check the ledger exists to allow beyond the blend: whether the
    projection that ranks a squad near the top is the one that finishes it at
    the bottom. Managers are matched by name, the key both reads share; equal
    values keep their stored order.
    """
    projected = document.get("league_projection") or {}
    scored = {
        row["name"]: row["points"]
        for row in (document.get("actual") or {}).get("league_points") or []
    }
    names = [name for name in projected if name in scored]
    by_projection = sorted(names, key=lambda name: -projected[name])
    by_points = sorted(names, key=lambda name: -scored[name])
    return [
        {
            "manager": name,
            "projected": projected[name],
            "projected_rank": by_projection.index(name) + 1,
            "points": scored[name],
            "points_rank": by_points.index(name) + 1,
        }
        for name in by_projection
    ]


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
        totals = outcome_totals(document)
        if totals is None:
            continue
        blended, jp_only = totals
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


def next_round_to_collect(documents: list, finished_ids: set) -> int | None:
    """The oldest stored round Biwenger calls finished that has no outcome.

    One per run, oldest first. A backlog then drains a round a day rather
    than spending a whole morning's request budget in a single spike, on a
    path that shares its rate limit with the phone app.

    Presence of the key decides, not its contents: a round whose outcome is
    legitimately empty must not be re-read every morning for the rest of the
    season.

    A round Biwenger has not finished is skipped rather than read early:
    under *jornada única* it is not final until every match in it is played,
    so an early read would store a partial total as though it were the
    result — and the outcome of a finished round never changes, which is the
    only reason caching it is safe at all.
    """
    pending = [
        document.get("round_id")
        for document in documents or []
        if document.get("round_id") in (finished_ids or set())
        and "actual" not in document
    ]
    return min(pending) if pending else None


def oraculo_scales(page_rows: list, picks: dict) -> dict:
    """`{slug: {"page", "api", "chance"}}` for every player Oráculo projects
    both on its predictions page and in its API lists, for the same fixture.

    The two disagree by more than a constant; keeping both on the same morning
    is what lets graded rounds say which one tracks Biwenger's points. The API
    lists carry only the ~60 players Oráculo recommends.
    """
    api = {
        (entry.get("playerId"), entry.get("fixtureId")): entry
        for entries in (picks or {}).values()
        for entry in entries or []
    }
    out = {}
    for row in page_rows or []:
        pick = api.get((row.get("playerId"), row.get("fixtureId")))
        if pick is None or row.get("slug") is None:
            continue
        out[row["slug"]] = {
            "page": row.get("predictedPoints"),
            "api": pick.get("predictedPoints"),
            "chance": row.get("chance"),
        }
    return out


def league_jp(rows: list) -> dict[str, int]:
    """Jornada Perfecta's SF for every row it projects, keyed by the Biwenger
    id as a string (Firestore map keys must be strings). A player it does not
    project is left out: no projection is not a projection of zero."""
    out = {}
    for row in rows:
        jp_sf = _jp_sf(row)
        if jp_sf is not None and row.get("bw_id") is not None:
            out[str(row["bw_id"])] = jp_sf
    return out


# A capture is the last projection before the round's first kick-off, and a
# round is over within a few days of it. A refusal still standing a week on is
# not a report Biwenger has yet to file; it is one it filed somewhere else.
REFUSAL_FINAL_AFTER = timedelta(days=7)


def refusal_is_final(document: dict, now: datetime) -> bool:
    """Whether a round refused for missing reports should stop being retried:
    its capture is at least `REFUSAL_FINAL_AFTER` old. A document with no
    readable capture date is retried, never given up on."""
    try:
        captured = datetime.fromisoformat(document["captured_at"])
    except (KeyError, TypeError, ValueError):
        return False
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=now.tzinfo)
    return now - captured >= REFUSAL_FINAL_AFTER


def refused_outcome(missing: list, now: datetime) -> dict:
    """The outcome stored for a round given up on: why, and who had no report.
    No points of any kind, so nothing grades or ranks it, and its presence
    keeps `next_round_to_collect` from choosing it again."""
    return {
        "refused": "missing_reports",
        "missing": sorted(missing),
        "fetched_at": now.isoformat(),
    }


def _matchday_name(name: str | None) -> str | None:
    """ "Jornada 6 (aplazada)" → "Jornada 6"; `None` when there is no name."""
    return name.split(" (")[0].strip() if name else None


def matchday_ids(round_id: int, season_rounds: list) -> list[int]:
    """Every round id of the matchday `round_id` belongs to, ascending.

    Biwenger files a postponed match under a new round id named after its
    matchday ("Jornada 6 (aplazada)", twice for J6). A round the season does
    not list, or lists with no name, is its own matchday.
    """
    names = {r.get("id"): _matchday_name(r.get("name")) for r in season_rounds}
    name = names.get(round_id)
    if name is None:
        return [round_id]
    return sorted(rid for rid, n in names.items() if n == name)


def finished_matchdays(season_rounds: list, finished: set) -> set:
    """The ids in `finished` whose whole matchday is finished. A postponed
    game still to play holds back every id of its matchday, so the matchday
    is neither read nor refused before it is complete."""
    return {
        rid
        for rid in finished
        if all(i in finished for i in matchday_ids(rid, season_rounds))
    }


def covering_round(round_id: int, matchday: list, documents: list) -> int | None:
    """Another round of the same matchday whose stored outcome already holds
    it, or `None`. A refused or itself-covered outcome holds nothing."""
    for document in documents or []:
        other = document.get("round_id")
        actual = document.get("actual")
        if other == round_id or other not in matchday or not actual:
            continue
        if actual.get("refused") or actual.get("covered_by"):
            continue
        return other
    return None


def covered_outcome(covering: int, now: datetime) -> dict:
    """The outcome stored for a round whose matchday another round holds. No
    points, so it is never graded or ranked twice; a projection captured for
    it was never the eleven Biwenger applied."""
    return {"covered_by": covering, "fetched_at": now.isoformat()}
