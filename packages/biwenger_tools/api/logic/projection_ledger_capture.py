"""Capture what was projected, before the round it applies to kicks off.

Lives apart from both the digest and the lineup pick because it belongs to
neither: it records the decision they are about to make, and must survive
either of them failing.
"""

import time
from datetime import datetime

from core.constants import MADRID_TZ
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import projection_ledger, projection_ledger_store
from packages.biwenger_tools.api.logic.real_points import (
    missing_reports,
    personalizado,
    reports_for_round,
)
from packages.biwenger_tools.api.logic.rows import build_squad_rows

logger = get_logger(__name__)


def _round_name_for(round_data: dict, round_id: int) -> str | None:
    """The round's own `name`, whichever of (current, `next`) matched."""
    if round_data.get("id") == round_id:
        return round_data.get("name")
    return (round_data.get("next") or {}).get("name")


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
        snapshot = projection_ledger.build_snapshot(
            round_id,
            _round_name_for(round_data, round_id),
            config.CURRENT_SEASON,
            rows,
            now,
        )
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


def _outcome_for(ctx, round_id: int) -> dict | None:
    """One finished round's real points, or `None` if any player is missing.

    An absent report scores zero through `personalizado`, which is the same
    number as a dreadful afternoon — so a partial read would be stored as a
    result and never questioned. Refusing the whole round leaves it pending
    for tomorrow instead, which costs a day and cannot lie.
    """
    round_league = ctx.biwenger.get_round_league(round_id)
    applied = projection_ledger.extract_applied_lineup(
        round_league, ctx.biwenger.user_id
    )
    if applied is None:
        return None

    points = {}
    for bw_id in sorted(set(applied["player_ids"])):
        player = (ctx.biwenger_players or {}).get(bw_id) or {}
        slug = player.get("slug")
        if not slug:
            continue
        detail = ctx.biwenger.get_player_reports(slug)
        matches = reports_for_round(detail.get("reports") or [], round_id)
        points[bw_id] = personalizado(matches, detail.get("position"))["points"]
        time.sleep(_PLAYER_READ_DELAY)

    if missing_reports(applied["player_ids"], points):
        return None
    return {
        "fetched_at": datetime.now(MADRID_TZ).isoformat(),
        "applied": applied,
        "player_points": points,
        "applied_total": projection_ledger.xi_real_points(
            applied["player_ids"], applied["captain_id"], points
        ),
    }


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
        finished = {
            r.get("id")
            for r in ((round_data.get("season") or {}).get("rounds") or [])
            if r.get("status") == "finished"
        }
        documents = projection_ledger_store.list_all()
        round_id = projection_ledger.next_round_to_collect(documents, finished)
        if round_id is None:
            return {"skipped": "nothing_pending"}

        outcome = _outcome_for(ctx, round_id)
        if outcome is None:
            return {"skipped": "incomplete", "round_id": round_id}

        season = next(
            (d.get("season") for d in documents if d.get("round_id") == round_id),
            config.CURRENT_SEASON,
        )
        projection_ledger_store.write_actual(season, round_id, outcome)
        return {"collected": round_id, "points": outcome["applied_total"]}
    except Exception as exc:
        logger.exception("Projection ledger collection failed.")
        return {"error": str(exc)}
