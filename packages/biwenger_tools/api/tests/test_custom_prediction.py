"""Tests for `logic/custom_prediction.py` — the Oráculo blend.

JP stays the base; Oráculo only ever nudges it. Every case here is one of
the three fallbacks (no opinion, blend off, unmatched) or one of the
regression rows measured against the owner's real squad — never an
assertion of whatever the code happens to compute today.
"""

from packages.biwenger_tools.api.logic import custom_prediction as cp
from packages.biwenger_tools.api.logic.player_matching import build_jp_index
from packages.biwenger_tools.api.logic.rows import build_oraculo_index
from packages.biwenger_tools.api.player_formatting import SCORE_SF


def _row(oraculo_points=None, matched=True, chance=80, lists=None, jp_sf=None):
    jp_player = None
    if jp_sf is not None:
        jp_player = {"predict": [{"type": SCORE_SF, "rate": jp_sf}]}
    return {
        "jp_player": jp_player,
        "oraculo_matched": matched,
        "oraculo_points": oraculo_points,
        "oraculo_chance": chance,
        "oraculo_lists": lists or [],
    }


def _scale(k: float, top: float = 10.0) -> cp.ProjectionScale:
    """A two-point scale that reproduces a constant multiplier exactly:
    interpolating between (0, top) and (0, top * k) gives `points * k` for
    any `points` in [0, top] — reused so the pre-existing clamp/chance/list
    tests keep their old expected numbers under the new API."""
    return cp.ProjectionScale(oraculo=(0.0, top), jp=(0.0, top * k))


def _realistic_population() -> list[tuple[int, float]]:
    """40 lower-tier + 10 top-tier `(jp_sf, oraculo_points)` readings, shaped
    after a real read: most players sit low on both scales, but Oráculo's
    floor compresses that majority far more than JP does, so no single ratio
    describes both ends (`jp/oraculo` ~91 for the bulk, ~133 at the top)."""
    low = []
    for i in range(40):
        t = i / 39
        jp = round(12 + t * (430 - 12))
        points = round(0.8 + t * (4.2 - 0.8), 2)
        low.append((jp, points))
    high = []
    for i in range(10):
        t = i / 9
        jp = round(430 + t * (943 - 430))
        points = round(4.2 + t * (9.0 - 4.2), 2)
        high.append((jp, points))
    return low + high


# --- custom_prediction: the three short-circuits ---------------------------


def test_an_unmatched_row_returns_jp_sf_untouched():
    """Oráculo not carrying this player is the normal state for most of a
    squad most of the week; it must never move the number Oráculo cannot
    speak to."""
    row = _row(matched=False, oraculo_points=None)
    assert cp.custom_prediction(row, jp_sf=500, scale=_scale(131), blend_on=True) == 500


def test_blend_off_returns_jp_sf_even_when_matched():
    """`ORACULO_MIN_COVERAGE` switches the whole read off; a matched row
    must not sneak the blend back in just because it personally has data."""
    row = _row(oraculo_points=4.17)
    result = cp.custom_prediction(row, jp_sf=404, scale=_scale(131), blend_on=False)
    assert result == 404


def test_no_scale_returns_jp_sf_unchanged():
    """`scale=None` means `build_scale` had nothing to compute from (empty
    or fully unmatched read) — there is no percentile map to convert into,
    so the blend cannot run."""
    row = _row(oraculo_points=4.17)
    assert cp.custom_prediction(row, jp_sf=404, scale=None, blend_on=True) == 404


def test_matched_with_no_points_returns_jp_sf_unchanged():
    """`oraculo_matched=True` with no `oraculo_points` is "carries him with
    no projection" — a different state from "not carried" but the same
    outcome: no opinion, no move."""
    row = _row(oraculo_points=None, matched=True)
    assert cp.custom_prediction(row, jp_sf=250, scale=_scale(131), blend_on=True) == 250


# --- the clamp: the whole point of this module -----------------------------


def test_the_clamp_stops_a_backup_keeper_being_inflated_212_percent():
    """The regression that found the clamp: Fortuño JP 12, Oráculo 0.74,
    equivalent to a x131 multiplier, blends unclamped to 37 (+212%) — a
    backup keeper "will not play" becoming a near-average score purely for
    existing in Oráculo's feed. Clamped at ±25% it must land at 15, not 37."""
    row = _row(oraculo_points=0.74)
    result = cp.custom_prediction(row, jp_sf=12, scale=_scale(131), blend_on=True)
    assert result == 15
    assert result != 37


def test_a_player_in_the_body_of_the_distribution_is_unaffected_by_the_clamp():
    """Dmitrovic JP 404, Oráculo 4.17, x131 blends to 447 (+11%), well
    inside ±25% — the clamp must be a no-op here, not just theoretically
    but bit-for-bit against the unclamped blend."""
    row = _row(oraculo_points=4.17)
    result = cp.custom_prediction(row, jp_sf=404, scale=_scale(131), blend_on=True)
    assert result == 447


# --- chance: a guard, never a bonus -----------------------------------------


def test_a_low_chance_damps_the_movement_toward_jp_sf():
    """Below `ORACULO_CHANCE_FLOOR` the contribution is damped toward jp_sf
    rather than boosted — a number built on a player who probably will not
    play should move JP's number less, never more."""
    high_chance_row = _row(oraculo_points=4.17, chance=80)
    low_chance_row = _row(oraculo_points=4.17, chance=10)
    scale = _scale(131)
    undamped = cp.custom_prediction(
        high_chance_row, jp_sf=404, scale=scale, blend_on=True
    )
    damped = cp.custom_prediction(low_chance_row, jp_sf=404, scale=scale, blend_on=True)
    assert undamped == 447
    assert abs(damped - 404) < abs(undamped - 404)


# --- the list bonus: stacks, and excludes chollos/capitanes -----------------


def test_three_qualifying_lists_give_nine_percent():
    """Capped at three lists, so the bonus stays secondary to the blend."""
    row = _row(
        oraculo_points=1.0,
        lists=["goleadores", "asistentes", "porteros"],
    )
    # A x100 scale makes equiv == jp_sf, so the blend itself is a no-op and
    # the +9% below is entirely the list bonus.
    result = cp.custom_prediction(row, jp_sf=100, scale=_scale(100), blend_on=True)
    assert result == 109


def test_chollos_and_capitanes_give_no_bonus():
    """`chollos` ranks value, not quality, and `capitanes` is derived from
    the other lists — neither belongs in a points number."""
    row = _row(oraculo_points=1.0, lists=["chollos", "capitanes"])
    result = cp.custom_prediction(row, jp_sf=100, scale=_scale(100), blend_on=True)
    assert result == 100


def test_a_fourth_qualifying_list_does_not_exceed_the_cap():
    row = _row(
        oraculo_points=1.0,
        lists=["goleadores", "asistentes", "porteros", "defensas"],
    )
    result = cp.custom_prediction(row, jp_sf=100, scale=_scale(100), blend_on=True)
    assert result == 109


# --- qualifying_lists --------------------------------------------------------


def test_qualifying_lists_excludes_chollos_and_capitanes_and_sorts():
    row = _row(lists=["capitanes", "porteros", "chollos", "asistentes"])
    assert cp.qualifying_lists(row) == ["asistentes", "porteros"]


# --- build_scale: a percentile map, not a pairing ---------------------------


def test_build_scale_sorts_each_sequence_independently():
    """A percentile map, not a pairing: the two sequences are ranked on
    their own terms. Oráculo's best-rated player here has a low JP number
    (a disagreement, not a floor) — the map must still send the *top*
    Oráculo reading to the *top* JP number. Sorting jointly by the original
    pairing would send it to the low one instead."""
    rows = [_row(oraculo_points=1.0, jp_sf=500), _row(oraculo_points=9.0, jp_sf=100)]
    scale = cp.build_scale(rows)
    assert scale.oraculo == (1.0, 9.0)
    assert scale.jp == (100, 500)
    assert cp.equivalent_jp(scale, 9.0) == 500


def test_build_scale_ignores_unmatched_and_zero_point_rows():
    rows = [
        _row(oraculo_points=None, matched=False, jp_sf=100),
        _row(oraculo_points=0.0, jp_sf=999),
        _row(oraculo_points=2.0, jp_sf=200),
    ]
    scale = cp.build_scale(rows)
    assert scale == cp.ProjectionScale(oraculo=(2.0,), jp=(200,))


def test_build_scale_is_none_on_empty_input():
    assert cp.build_scale([]) is None


def test_build_scale_is_none_when_nothing_is_matched():
    rows = [_row(oraculo_points=None, matched=False, jp_sf=100)]
    assert cp.build_scale(rows) is None


def test_build_scale_with_one_matched_player_still_produces_a_usable_scale():
    """A single data point is a degenerate scale, not an absent one — every
    reading clamps to that one player's JP number rather than the read
    falling back to no blend at all."""
    rows = [_row(oraculo_points=4.0, jp_sf=300)]
    scale = cp.build_scale(rows)
    assert scale == cp.ProjectionScale(oraculo=(4.0,), jp=(300,))
    assert cp.equivalent_jp(scale, 4.0) == 300
    assert cp.equivalent_jp(scale, 999) == 300


def test_build_scale_with_every_player_sharing_one_oraculo_value():
    """All-tied input must not crash the scale builder or the lookup — every
    reading still resolves to one of the tied group's JP values."""
    rows = [
        _row(oraculo_points=2.0, jp_sf=100),
        _row(oraculo_points=2.0, jp_sf=300),
        _row(oraculo_points=2.0, jp_sf=200),
    ]
    scale = cp.build_scale(rows)
    assert scale.oraculo == (2.0, 2.0, 2.0)
    assert scale.jp == (100, 200, 300)
    assert cp.equivalent_jp(scale, 2.0) in scale.jp


# --- equivalent_jp: interpolates, clamps, never divides by a tied gap ------


def test_equivalent_jp_is_monotonic_even_with_duplicate_oraculo_values():
    """A higher Oráculo reading must never convert to a lower JP equivalent
    — the property a naive nearest-neighbour lookup could violate on ties,
    and the one a real Oráculo population (heavy duplicate runs at the
    bottom) actually exercises."""
    scale = cp.ProjectionScale(
        oraculo=(0.5, 0.5, 0.5, 2.0, 2.0, 5.0, 9.0),
        jp=(10, 15, 20, 100, 120, 400, 900),
    )
    readings = [0.1, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 9.0, 12.0]
    converted = [cp.equivalent_jp(scale, r) for r in readings]
    assert converted == sorted(converted)


def test_equivalent_jp_clamps_outside_the_population_instead_of_extrapolating():
    scale = cp.ProjectionScale(oraculo=(1.0, 5.0, 9.0), jp=(50, 400, 900))
    assert cp.equivalent_jp(scale, 0.1) == 50
    assert cp.equivalent_jp(scale, 20.0) == 900


# --- the headline regression: the top of the range is not dragged down -----


def test_the_top_of_the_range_is_not_dragged_below_his_own_jp_projection():
    """The defect the percentile scale replaces a multiplier for: a global
    median ratio undershoots the top tier's own ratio (the floor makes the
    bulk of the population look cheaper in Oráculo terms than it is), so the
    league's best projection got blended DOWN — 943 to ~913 with a median
    `k`. A percentile map sends the best Oráculo reading to the best JP
    reading, never below it."""
    population = _realistic_population()
    rows = [_row(oraculo_points=points, jp_sf=jp) for jp, points in population]
    scale = cp.build_scale(rows)
    jp_top, points_top = population[-1]
    top_row = _row(oraculo_points=points_top, jp_sf=jp_top)
    blended = cp.custom_prediction(top_row, jp_sf=jp_top, scale=scale, blend_on=True)
    assert blended >= jp_top


def test_a_mid_table_player_converts_close_to_his_own_jp_level():
    """A player in the body of the distribution must land near his own JP
    number, not get pulled toward whatever the population's overall ratio
    happens to be — the failure mode a single multiplier cannot avoid."""
    population = _realistic_population()
    rows = [_row(oraculo_points=points, jp_sf=jp) for jp, points in population]
    scale = cp.build_scale(rows)
    jp_mid, points_mid = population[20]
    mid_row = _row(oraculo_points=points_mid, jp_sf=jp_mid)
    blended = cp.custom_prediction(mid_row, jp_sf=jp_mid, scale=scale, blend_on=True)
    assert abs(blended - jp_mid) <= jp_mid * 0.05


# --- should_blend -------------------------------------------------------------


def test_should_blend_is_true_at_or_above_the_threshold():
    rows = [_row(matched=True), _row(matched=True), _row(matched=False)]
    assert cp.should_blend(rows, coverage_min=0.60) is True


def test_should_blend_is_false_below_the_threshold():
    """Coverage 1/3 must not scrape by on a 0.60 floor — a partial blend
    is worse than none: whoever Oráculo happened to look at first would
    jump the queue for no reason anyone could see."""
    rows = [_row(matched=True), _row(matched=False), _row(matched=False)]
    assert cp.should_blend(rows, coverage_min=0.60) is False


# --- global_scale: the scale over the whole population, not a table --------


def test_global_scale_matches_build_scale_over_the_same_population():
    """The whole point of computing the scale once per request: a caller
    passing the full player population must get that population's scale,
    not something a smaller table would have derived on its own."""
    biwenger_players = {
        1: {"id": 1, "name": "A", "position": 3, "price": 1},
        2: {"id": 2, "name": "B", "position": 3, "price": 1},
        3: {"id": 3, "name": "C", "position": 3, "price": 1},
    }
    jp_index = build_jp_index(
        [
            {"name": "A", "slug": "a", "predict": [{"type": SCORE_SF, "rate": 100}]},
            {"name": "B", "slug": "b", "predict": [{"type": SCORE_SF, "rate": 200}]},
            {"name": "C", "slug": "c", "predict": [{"type": SCORE_SF, "rate": 50}]},
        ]
    )
    oraculo_index = build_oraculo_index(
        [
            {"playerName": "A", "slug": "a", "predictedPoints": 1.0, "chance": 80},
            {"playerName": "B", "slug": "b", "predictedPoints": 2.0, "chance": 80},
            {"playerName": "C", "slug": "c", "predictedPoints": 2.0, "chance": 80},
        ]
    )
    scale = cp.global_scale(biwenger_players, jp_index, oraculo_index)
    assert scale == cp.ProjectionScale(oraculo=(1.0, 2.0, 2.0), jp=(50, 100, 200))


def test_global_scale_is_none_with_no_oraculo_data():
    biwenger_players = {1: {"id": 1, "name": "A", "position": 3, "price": 1}}
    jp_index = build_jp_index([{"name": "A", "slug": "a"}])
    assert cp.global_scale(biwenger_players, jp_index, {}) is None
