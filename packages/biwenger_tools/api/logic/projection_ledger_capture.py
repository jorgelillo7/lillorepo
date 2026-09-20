"""Capture what was projected, before the round it applies to kicks off.

Lives apart from both the digest and the lineup pick because it belongs to
neither: it records the decision they are about to make, and must survive
either of them failing.
"""

from datetime import datetime

from core.constants import MADRID_TZ
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import projection_ledger, projection_ledger_store
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
