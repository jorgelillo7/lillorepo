"""Capture what was projected, before the round it applies to kicks off.

Lives apart from both the digest and the lineup pick because it belongs to
neither: it records the decision they are about to make, and must survive
either of them failing.
"""

import time
from datetime import datetime

from core.constants import MADRID_TZ
from core.sdk import oraculo
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import (
    league_compare,
    projection_ledger,
    projection_ledger_store,
)
from packages.biwenger_tools.api.logic.real_points import (
    missing_reports,
    personalizado,
    reports_for_rounds,
)
from packages.biwenger_tools.api.logic.rows import build_squad_rows

logger = get_logger(__name__)


def _round_name_for(round_data: dict, round_id: int) -> str | None:
    """The round's own `name`, whichever of (current, `next`) matched."""
    if round_data.get("id") == round_id:
        return round_data.get("name")
    return (round_data.get("next") or {}).get("name")


def _oraculo_scales() -> dict:
    """Both Oráculo scales for this matchday, from the hour's cached reads."""
    picks = oraculo.fetch_picks()
    page = oraculo.rows_for_dates(
        oraculo.fetch_predictions(), oraculo.matchday_dates(picks)
    )
    return projection_ledger.oraculo_scales(page, picks.get("picks") or {})


def capture(ctx) -> dict:
    """Snapshot the blend against Jornada Perfecta alone for the round the
    lineup pick actually lands on. Never raises, and never writes once that
    round may already have kicked off — see `projection_ledger.target_round`.

    Hangs off the lineup pick rather than off the digest, so that **forcing**
    one captures too: `/alinear` is the button pressed to refine before a
    round closes, which is exactly when the projection is worth keeping. The
    digest chains that same pick, so it captures once rather than twice.

    Called before anything is written to Biwenger, so a failure applying the
    lineup cannot cost the record of what was projected. Reads its own squad
    and round rather than borrowing the pick's, keeping a failure in either
    from reaching the other.
    """
    try:
        round_data = ctx.biwenger.get_round()
        now = datetime.now(MADRID_TZ)
        round_id = projection_ledger.target_round(round_data, now)
        if round_id is None:
            return {"skipped": "kicked_off_or_unknown"}

        my_squad = ctx.biwenger.get_manager_squad(
            config.USER_SQUAD_URL, ctx.biwenger.user_id
        )
        rows = build_squad_rows(
            my_squad,
            ctx.biwenger_players,
            ctx.jp_index,
            ctx.oraculo_index,
            oraculo_scale=ctx.oraculo_scale,
        )
        round_name = _round_name_for(round_data, round_id)
        snapshot = projection_ledger.build_snapshot(
            round_id,
            round_name,
            config.CURRENT_SEASON,
            rows,
            now,
        )
        # Every squad's projected eleven, from the same morning as ours. It is
        # the extra, not the record: a failed read leaves our projection whole.
        try:
            league = league_compare.collect_cached(ctx)
            snapshot["league_projection"] = {
                name: entry["eleven"] for name, entry in league.items()
            }
        except Exception:
            logger.exception(
                "League projection not captured; ours is stored without it."
            )
        # Every player Jornada Perfecta projects, so whether a fixture moves its
        # number can be measured on the whole competition, not on our squad.
        try:
            everyone = [{"id": bw_id} for bw_id in ctx.biwenger_players or {}]
            snapshot["league_jp"] = projection_ledger.league_jp(
                build_squad_rows(everyone, ctx.biwenger_players, ctx.jp_index)
            )
        except Exception:
            logger.exception("League JP not captured; ours is stored without it.")
        # Each team's win and clean-sheet chances for the round, so a captain
        # or a defender chosen on them can be graded once rounds accumulate.
        try:
            number = (round_name or "").rsplit(" ", 1)[-1]
            snapshot["team_outlook"] = [
                row
                for row in oraculo.fetch_team_outlook()
                if number.isdigit() and row.get("matchday") == int(number)
            ]
        except Exception:
            logger.exception("Team outlook not captured; ours is stored without it.")
        # Oráculo's points as its page and its API give them, which disagree.
        try:
            snapshot["oraculo_scales"] = _oraculo_scales()
        except Exception:
            logger.exception("Oráculo scales not captured; ours is stored without it.")
        projection_ledger_store.write(snapshot)
        return {
            "written": True,
            "round_id": round_id,
            "xi_differs": snapshot["xi_differs"],
        }
    except Exception as exc:
        logger.exception("Projection ledger capture failed.")
        return {"error": str(exc)}


# One second between player reads. The window is shared with the phone app,
# and a 429 spends it for both.
_PLAYER_READ_DELAY = 1.0


def _outcome_for(
    ctx, round_id: int, squad_ids=(), matchday=None
) -> tuple[dict | None, list]:
    """One finished round's real points — for the eleven fielded and for
    every other player in `squad_ids`, so the record shows what the bench
    scored too — or `None` if a fielded player's reports are missing.

    An absent report scores zero through `personalizado`, which is the same
    number as a dreadful afternoon — so a partial read would be stored as a
    result and never questioned. Refusing the whole round leaves it pending
    for tomorrow instead, which costs a day and cannot lie.
    """
    matchday = matchday or [round_id]
    round_league = ctx.biwenger.get_round_league(round_id)
    applied = projection_ledger.extract_applied_lineup(
        round_league, ctx.biwenger.user_id
    )
    if applied is None:
        return None, []

    points, counted = {}, {}
    for bw_id in sorted(set(applied["player_ids"]) | set(squad_ids)):
        player = (ctx.biwenger_players or {}).get(bw_id) or {}
        slug = player.get("slug")
        if not slug:
            continue
        detail = ctx.biwenger.get_player_reports(slug)
        matches = reports_for_rounds(detail.get("reports") or [], matchday)
        points[bw_id] = personalizado(matches, detail.get("position"))["points"]
        counted[bw_id] = len(matches)
        time.sleep(_PLAYER_READ_DELAY)

    missing = missing_reports(applied["player_ids"], points, counted)
    if missing:
        return None, missing
    return {
        "fetched_at": datetime.now(MADRID_TZ).isoformat(),
        "applied": applied,
        "player_points": points,
        "league_points": projection_ledger.extract_league_points(round_league),
        "applied_total": projection_ledger.xi_real_points(
            applied["player_ids"], applied["captain_id"], points
        ),
    }, []


def collect(ctx) -> dict:
    """Store the outcome of one finished round that has none yet.

    Runs beside the capture rather than in a script somebody has to remember:
    a ledger that depends on a human running a command is a ledger that ends
    up half empty, and the half it loses is the recent half.

    One round per run, oldest first, and never raises — it sits next to a
    step that applies a lineup unattended, and a rate limit on a reporting
    read must not reach it.
    """
    try:
        round_data = ctx.biwenger.get_round()
        season_rounds = (round_data.get("season") or {}).get("rounds") or []
        finished = projection_ledger.finished_matchdays(
            season_rounds,
            {r.get("id") for r in season_rounds if r.get("status") == "finished"},
        )
        documents = projection_ledger_store.list_all()
        round_id = projection_ledger.next_round_to_collect(documents, finished)
        if round_id is None:
            return {"skipped": "nothing_pending"}

        snapshot: dict = next(
            (d for d in documents if d.get("round_id") == round_id), {}
        )
        season = snapshot.get("season") or config.CURRENT_SEASON
        matchday = projection_ledger.matchday_ids(round_id, season_rounds)
        covering = projection_ledger.covering_round(round_id, matchday, documents)
        if covering is not None:
            projection_ledger_store.write_actual(
                season,
                round_id,
                projection_ledger.covered_outcome(covering, datetime.now(MADRID_TZ)),
            )
            return {"covered": round_id, "by": covering}

        squad_ids = [p["bw_id"] for p in snapshot.get("players") or []]
        outcome, missing = _outcome_for(ctx, round_id, squad_ids, matchday=matchday)
        if outcome is None:
            now = datetime.now(MADRID_TZ)
            if missing and projection_ledger.refusal_is_final(snapshot, now):
                projection_ledger_store.write_actual(
                    season, round_id, projection_ledger.refused_outcome(missing, now)
                )
                return {"refused": round_id, "missing": len(missing)}
            return {"skipped": "incomplete", "round_id": round_id}

        projection_ledger_store.write_actual(season, round_id, outcome)
        return {"collected": round_id, "points": outcome["applied_total"]}
    except Exception as exc:
        logger.exception("Projection ledger collection failed.")
        return {"error": str(exc)}
