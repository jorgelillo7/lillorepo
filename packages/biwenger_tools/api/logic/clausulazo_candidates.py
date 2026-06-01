"""Shared helpers to enumerate rival clausulazo candidates.

Used by `recommendations.run_recommendations` (top-N per position, with
margin) and `emergency.preview_clausulazo` (top-1 in a chosen position,
with cash-justo / no margin). Kept here so both flows agree on:

- which players are excluded (mine, clause-locked, no SF score, GK
  with only 1 GK in the rival squad — the "don't break a rival" house rule);
- which fields a candidate row carries (incl. `owner_user_id`, needed
  by `place_clausulazo` for the `to=<seller>` payload field).
"""

import time

from core.sdk.biwenger import BiwengerClient
from core.sdk.jp import get_predict_rate
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.rows import build_squad_rows
from packages.biwenger_tools.api.player_formatting import SCORE_SF

logger = get_logger(__name__)

GK_POSITION_ID = 1


def sf_of(row: dict) -> int:
    jp = row.get("jp_player")
    if not jp:
        return 0
    return get_predict_rate(jp, SCORE_SF) or 0


def gather_rivals(
    biwenger: BiwengerClient,
    biwenger_players: dict,
    jp_index: dict,
) -> list[dict]:
    """Build the rival_rows list, tagged with owner name + user id.

    Skips the logged-in user's own squad. Each row carries:
    - `owner` (manager name) — used by the recommendations message.
    - `owner_user_id` (manager id) — used by emergency to fill
      `place_clausulazo`'s `to=<seller_user_id>` payload field.
    - `owner_gk_count` — used by `filter_affordable` to enforce the
      "don't leave a rival with zero GKs" house rule.
    """
    managers = biwenger.get_league_users(config.LEAGUE_DATA_URL)
    rivals: list[dict] = []
    for manager_id, manager_name in managers.items():
        if manager_id == biwenger.user_id:
            continue
        squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, manager_id)
        rows = build_squad_rows(squad, biwenger_players, jp_index, include_clause=True)
        gk_count = sum(1 for r in rows if r.get("position_id") == GK_POSITION_ID)
        for r in rows:
            r["owner"] = manager_name
            r["owner_user_id"] = manager_id
            r["owner_gk_count"] = gk_count
            rivals.append(r)
        time.sleep(0.3)
    return rivals


def filter_affordable(candidates: list[dict], my_ids: set, target: int) -> list[dict]:
    """Keep candidates I can actually afford (clause ≤ target) and skip mine.

    Also enforces the house rule that we never clauselazo a rival's only
    goalkeeper — Biwenger would technically allow it but the league agreed
    leaving someone with zero GKs is unsportsmanlike. The same rule does
    not apply to outfield positions (rivals are expected to rebuild).
    """
    out: list[dict] = []
    for row in candidates:
        if row.get("bw_id") in my_ids:
            continue
        if not row.get("clausulable_now", False):
            continue
        clause = row.get("clause_value") or 0
        if clause <= 0 or clause > target:
            continue
        if sf_of(row) <= 0:
            continue
        if (
            row.get("position_id") == GK_POSITION_ID
            and (row.get("owner_gk_count") or 0) <= 1
        ):
            continue
        out.append(row)
    return out
