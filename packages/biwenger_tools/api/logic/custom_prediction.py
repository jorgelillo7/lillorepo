"""The Oráculo blend — one number, JP as the base.

Pure functions over rows already carrying `oraculo_points`, `oraculo_chance`
and `oraculo_lists` (see `logic/rows.py`). No I/O and no caller yet: this
module computes the projection, it does not decide who reads it.
"""

from statistics import median

from core.sdk.jp import get_predict_rate
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.rows import oraculo_coverage
from packages.biwenger_tools.api.player_formatting import SCORE_SF

# The eight Oráculo shortlists split in two: these six carry a real
# quality signal and feed the projection. `chollos` ranks value rather than
# quality (cheap players that score less) and `capitanes` is derived from
# the others (every 3-and-4-list player is on it) — both would double-count
# rather than add information, so both stay out.
QUALIFYING_LISTS = frozenset(
    {
        "goleadores",
        "asistentes",
        "porteros",
        "defensas",
        "centrocampistas",
        "delanteros",
    }
)


def _jp_sf(row: dict) -> int | None:
    return get_predict_rate(row.get("jp_player"), SCORE_SF)


def conversion_factor(rows: list) -> float | None:
    """Median of `jp_sf / oraculo_points` over matched, positively-scored rows.

    Self-calibrating rather than a constant: the two providers disagree
    wildly on individuals (37 to 210 observed) while agreeing on the
    population, and recomputing this per read means neither provider
    rescaling its own numbers can silently break the blend.
    """
    ratios = []
    for row in rows:
        if not row.get("oraculo_matched"):
            continue
        points = row.get("oraculo_points")
        if not points or points <= 0:
            continue
        jp_sf = _jp_sf(row)
        if not jp_sf:
            continue
        ratios.append(jp_sf / points)
    if not ratios:
        return None
    return median(ratios)


def qualifying_lists(row: dict) -> list[str]:
    return sorted(
        name for name in row.get("oraculo_lists") or [] if name in QUALIFYING_LISTS
    )


def custom_prediction(row: dict, jp_sf: int, k: float | None, *, blend_on: bool) -> int:
    """The one number: JP as the base, Oráculo as a bounded nudge on top.

    Falls straight back to `jp_sf` when there is nothing to blend with: the
    blend switched off for the whole read, this row carrying no Oráculo
    opinion at all, or no `k` to convert Oráculo's scale into JP's.
    """
    oraculo_points = row.get("oraculo_points")
    if (
        not blend_on
        or not row.get("oraculo_matched")
        or k is None
        or oraculo_points is None
    ):
        return jp_sf

    equiv = oraculo_points * k
    blended = jp_sf * (1 - config.ORACULO_W) + equiv * config.ORACULO_W

    # A plain weighted average drags outliers toward the population median
    # (a backup keeper at JP 12 blended to 37 purely for existing in the
    # feed) — bound the movement instead of trusting the average.
    max_move = jp_sf * config.ORACULO_MAX_MOVE
    blended = max(jp_sf - max_move, min(jp_sf + max_move, blended))

    # `chance` is a guard, not a bonus — the source number already has it
    # baked in (`expectedPoints == predictedPoints x chance`). Below the
    # floor, shrink the movement in proportion to how far below it the
    # chance is, rather than trusting an opinion built on a player who
    # probably will not play.
    chance = row.get("oraculo_chance")
    if chance is not None and chance < config.ORACULO_CHANCE_FLOOR:
        damping = max(chance, 0) / config.ORACULO_CHANCE_FLOOR
        blended = jp_sf + (blended - jp_sf) * damping

    n_qualifying = len(qualifying_lists(row))
    blended *= 1 + config.ORACULO_LIST_BONUS * min(n_qualifying, 3)

    return round(blended)


def should_blend(rows: list, coverage_min: float) -> bool:
    """All-or-nothing per read: below `coverage_min`, nobody in this read
    gets blended, because a partial blend promotes whoever Oráculo happened
    to have looked at first."""
    return oraculo_coverage(rows) >= coverage_min
