"""The Oráculo blend — one number, JP as the base.

Pure functions over rows already carrying `oraculo_points`, `oraculo_chance`
and `oraculo_lists` (see `logic/rows.py`). No I/O and no caller yet: this
module computes the projection, it does not decide who reads it.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass

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


@dataclass(frozen=True)
class ProjectionScale:
    """A percentile map between the two providers' scales.

    `oraculo` and `jp` are the matched, positively-scored population, each
    sorted ascending independently — a percentile in one sequence reads off
    the same-percentile value in the other. Plain data (two tuples): passed
    around instead of a closure, comparable in tests, picklable, and cheap to
    build once per request.
    """

    oraculo: tuple[float, ...]
    jp: tuple[float, ...]


def build_scale(rows: list) -> ProjectionScale | None:
    """The percentile scale over matched, positively-scored rows, or `None`.

    Replaces a single multiplier: the two providers are not proportional —
    Oráculo has a floor that a multiplier cannot see, so the same `k` either
    over- or under-converts depending on where in the range a player sits.
    A percentile map has no such assumption: a reading at rank N converts to
    whatever sits at rank N in the other provider's own range, immune to
    either one rescaling its numbers (the reason the conversion self-
    calibrates in the first place).
    """
    pairs = []
    for row in rows:
        if not row.get("oraculo_matched"):
            continue
        points = row.get("oraculo_points")
        if not points or points <= 0:
            continue
        jp_sf = _jp_sf(row)
        if not jp_sf:
            continue
        pairs.append((points, jp_sf))
    if not pairs:
        return None
    return ProjectionScale(
        oraculo=tuple(sorted(points for points, _ in pairs)),
        jp=tuple(sorted(jp_sf for _, jp_sf in pairs)),
    )


def equivalent_jp(scale: ProjectionScale, points: float) -> float:
    """The JP value at `points`' percentile in `scale`.

    Interpolates between neighbours rather than snapping to the nearest —
    snapping would quantise every player onto as many discrete values as the
    scale has entries and make ties out of players who differ. A reading
    outside the population clamps to the top/bottom JP value; it does not
    extrapolate. `bisect` keeps this O(log n) per player.
    """
    oraculo, jp = scale.oraculo, scale.jp
    if points <= oraculo[0]:
        return jp[0]
    if points >= oraculo[-1]:
        return jp[-1]
    lo = bisect_left(oraculo, points)
    hi = bisect_right(oraculo, points)
    if lo < hi:
        # `points` matches one or more entries exactly: any index in the
        # matching block keeps the mapping monotonic across its edges.
        return jp[(lo + hi - 1) // 2]
    span = oraculo[lo] - oraculo[lo - 1]
    fraction = (points - oraculo[lo - 1]) / span
    return jp[lo - 1] + fraction * (jp[lo] - jp[lo - 1])


def qualifying_lists(row: dict) -> list[str]:
    return sorted(
        name for name in row.get("oraculo_lists") or [] if name in QUALIFYING_LISTS
    )


def custom_prediction(
    row: dict, jp_sf: int, scale: ProjectionScale | None, *, blend_on: bool
) -> int:
    """The one number: JP as the base, Oráculo as a bounded nudge on top.

    Falls straight back to `jp_sf` when there is nothing to blend with: the
    blend switched off for the whole read, this row carrying no Oráculo
    opinion at all, or no `scale` to convert Oráculo's range into JP's.
    """
    oraculo_points = row.get("oraculo_points")
    if (
        not blend_on
        or not row.get("oraculo_matched")
        or scale is None
        or oraculo_points is None
    ):
        return jp_sf

    equiv = equivalent_jp(scale, oraculo_points)
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


def global_scale(
    biwenger_players: dict, jp_index: dict, oraculo_index: dict
) -> ProjectionScale | None:
    """`build_scale` over the whole player population, not a table.

    The scale is a conversion between two providers' ranges, not a property
    of which 15 players happen to be in front of a reader — building it from
    a table let the same player blend to a different number depending on
    who shared his table. The import is function-local: `rows.py` already
    imports `oraculo_coverage` from here, and a module-level import back
    would make the two modules initialise each other.
    """
    from packages.biwenger_tools.api.logic.rows import build_row

    rows = [
        build_row(player, jp_index, oraculo_index)
        for player in biwenger_players.values()
    ]
    return build_scale(rows)
