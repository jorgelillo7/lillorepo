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
from typing import TYPE_CHECKING

from core.sdk.biwenger import BiwengerClient
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.rows import build_squad_rows
from packages.biwenger_tools.api.player_formatting import shown_score

if TYPE_CHECKING:
    from packages.biwenger_tools.api.logic.custom_prediction import ProjectionScale

logger = get_logger(__name__)

GK_POSITION_ID = 1


def sf_of(row: dict) -> int:
    return shown_score(row) or 0


def gather_rivals(
    biwenger: BiwengerClient,
    biwenger_players: dict,
    jp_index: dict,
    oraculo_index: dict | None = None,
    oraculo_scale: "ProjectionScale | None" = None,
) -> list[dict]:
    """Build the rival_rows list, tagged with owner name + user id.

    Skips the logged-in user's own squad. Each row carries:
    - `owner` (manager name) — used by the recommendations message.
    - `owner_user_id` (manager id) — used by emergency to fill
      `place_clausulazo`'s `to=<seller_user_id>` payload field.
    - `owner_gk_count` — used by `filter_affordable` to enforce the
      "don't leave a rival with zero GKs" house rule.

    `oraculo_index`/`oraculo_scale` flow straight into `build_squad_rows` so
    every rival's row carries the same blend as the caller's own squad — a
    ranking that mixes blended and raw rows is not a ranking on one scale.
    """
    managers = biwenger.get_league_users(
        config.LEAGUE_DATA_URL, config.NON_PLAYING_MEMBER_IDS
    )
    rivals: list[dict] = []
    for manager_id, manager_name in managers.items():
        if manager_id == biwenger.user_id:
            continue
        squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, manager_id)
        rows = build_squad_rows(
            squad,
            biwenger_players,
            jp_index,
            oraculo_index,
            include_clause=True,
            oraculo_scale=oraculo_scale,
        )
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


def pick_top_in_position(
    candidates: list[dict], preferred_position: int
) -> tuple[dict | None, bool]:
    """Top SF in `preferred_position`; fall back to top SF overall.

    Returns `(candidate, in_preferred_position)`. When `in_preferred_position`
    is False the candidate is the best-SF rival overall — used by callers
    that want to surface "no DEF afford(able), going for the best SF
    instead" without owning the in-position filtering logic themselves.
    `(None, False)` when there are no candidates at all.
    """
    in_position = [c for c in candidates if c.get("position_id") == preferred_position]
    if in_position:
        in_position.sort(key=sf_of, reverse=True)
        return in_position[0], True
    if not candidates:
        return None, False
    candidates_sorted = sorted(candidates, key=sf_of, reverse=True)
    return candidates_sorted[0], False


def _pacted_ids(pacted: set) -> set:
    """The pact as ints, so a set written with string ids still matches."""
    out = set()
    for raw in pacted or ():
        try:
            out.add(int(raw))
        except (TypeError, ValueError):
            continue
    return out


def annotate_pact(rows: list[dict], pacted: set) -> None:
    """Stamp every row with `pacted`: is its owner under the non-aggression
    pact?

    Always sets the key, including to False, so no caller has to distinguish
    "not pacted" from "nobody ran this". `/recomendar` renders the flag and
    keeps the row; `/emergencia` uses `without_pacted` to drop it.
    """
    protected = _pacted_ids(pacted)
    for row in rows:
        row["pacted"] = row.get("owner_user_id") in protected


def without_pacted(rows: list[dict], pacted: set) -> list[dict]:
    """`rows` minus every player owned by a manager under the pact.

    A new list, never an edit in place: `/recomendar` must keep showing these
    players while `/emergencia` must not see them at all, and some flows build
    both views from one `gather_rivals` result.

    Deliberately not folded into `filter_affordable`, which both flows share —
    a veto applied there would hide the pact from `/recomendar` too, and the
    whole point is that it stays visible where the owner can override it.
    """
    protected = _pacted_ids(pacted)
    return [row for row in rows if row.get("owner_user_id") not in protected]
