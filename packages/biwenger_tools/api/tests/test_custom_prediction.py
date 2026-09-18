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


# --- custom_prediction: the three short-circuits ---------------------------


def test_an_unmatched_row_returns_jp_sf_untouched():
    """Oráculo not carrying this player is the normal state for most of a
    squad most of the week; it must never move the number Oráculo cannot
    speak to."""
    row = _row(matched=False, oraculo_points=None)
    assert cp.custom_prediction(row, jp_sf=500, k=131, blend_on=True) == 500


def test_blend_off_returns_jp_sf_even_when_matched():
    """`ORACULO_MIN_COVERAGE` switches the whole read off; a matched row
    must not sneak the blend back in just because it personally has data."""
    row = _row(oraculo_points=4.17)
    assert cp.custom_prediction(row, jp_sf=404, k=131, blend_on=False) == 404


def test_no_conversion_factor_returns_jp_sf_unchanged():
    """`k=None` means `conversion_factor` had nothing to compute from
    (empty or fully unmatched read) — there is no scale to convert into,
    so the blend cannot run."""
    row = _row(oraculo_points=4.17)
    assert cp.custom_prediction(row, jp_sf=404, k=None, blend_on=True) == 404


def test_matched_with_no_points_returns_jp_sf_unchanged():
    """`oraculo_matched=True` with no `oraculo_points` is "carries him with
    no projection" — a different state from "not carried" but the same
    outcome: no opinion, no move."""
    row = _row(oraculo_points=None, matched=True)
    assert cp.custom_prediction(row, jp_sf=250, k=131, blend_on=True) == 250


# --- the clamp: the whole point of this module -----------------------------


def test_the_clamp_stops_a_backup_keeper_being_inflated_212_percent():
    """The regression that found the clamp: Fortuño JP 12, Oráculo 0.74,
    k=131 blends unclamped to 37 (+212%) — a backup keeper "will not play"
    becoming a near-average score purely for existing in Oráculo's feed.
    Clamped at ±25% it must land at 15, not 37."""
    row = _row(oraculo_points=0.74)
    result = cp.custom_prediction(row, jp_sf=12, k=131, blend_on=True)
    assert result == 15
    assert result != 37


def test_a_player_in_the_body_of_the_distribution_is_unaffected_by_the_clamp():
    """Dmitrovic JP 404, Oráculo 4.17, k=131 blends to 447 (+11%), well
    inside ±25% — the clamp must be a no-op here, not just theoretically
    but bit-for-bit against the unclamped blend."""
    row = _row(oraculo_points=4.17)
    assert cp.custom_prediction(row, jp_sf=404, k=131, blend_on=True) == 447


# --- chance: a guard, never a bonus -----------------------------------------


def test_a_low_chance_damps_the_movement_toward_jp_sf():
    """Below `ORACULO_CHANCE_FLOOR` the contribution is damped toward jp_sf
    rather than boosted — a number built on a player who probably will not
    play should move JP's number less, never more."""
    high_chance_row = _row(oraculo_points=4.17, chance=80)
    low_chance_row = _row(oraculo_points=4.17, chance=10)
    undamped = cp.custom_prediction(high_chance_row, jp_sf=404, k=131, blend_on=True)
    damped = cp.custom_prediction(low_chance_row, jp_sf=404, k=131, blend_on=True)
    assert undamped == 447
    assert abs(damped - 404) < abs(undamped - 404)


# --- the list bonus: stacks, and excludes chollos/capitanes -----------------


def test_three_qualifying_lists_give_nine_percent():
    """Capped at three lists, so the bonus stays secondary to the blend."""
    row = _row(
        oraculo_points=1.0,
        lists=["goleadores", "asistentes", "porteros"],
    )
    # k=100 makes equiv == jp_sf, so the blend itself is a no-op and the
    # +9% below is entirely the list bonus.
    assert cp.custom_prediction(row, jp_sf=100, k=100, blend_on=True) == 109


def test_chollos_and_capitanes_give_no_bonus():
    """`chollos` ranks value, not quality, and `capitanes` is derived from
    the other lists — neither belongs in a points number."""
    row = _row(oraculo_points=1.0, lists=["chollos", "capitanes"])
    assert cp.custom_prediction(row, jp_sf=100, k=100, blend_on=True) == 100


def test_a_fourth_qualifying_list_does_not_exceed_the_cap():
    row = _row(
        oraculo_points=1.0,
        lists=["goleadores", "asistentes", "porteros", "defensas"],
    )
    assert cp.custom_prediction(row, jp_sf=100, k=100, blend_on=True) == 109


# --- qualifying_lists --------------------------------------------------------


def test_qualifying_lists_excludes_chollos_and_capitanes_and_sorts():
    row = _row(lists=["capitanes", "porteros", "chollos", "asistentes"])
    assert cp.qualifying_lists(row) == ["asistentes", "porteros"]


# --- conversion_factor -------------------------------------------------------


def test_conversion_factor_is_the_median_ratio_over_matched_rows():
    rows = [
        _row(oraculo_points=1.0, jp_sf=100),
        _row(oraculo_points=2.0, jp_sf=200),
        _row(oraculo_points=2.0, jp_sf=50),
    ]
    # ratios: 100, 100, 25 -> median 100
    assert cp.conversion_factor(rows) == 100


def test_conversion_factor_ignores_unmatched_and_zero_point_rows():
    rows = [
        _row(oraculo_points=None, matched=False, jp_sf=100),
        _row(oraculo_points=0.0, jp_sf=999),
        _row(oraculo_points=2.0, jp_sf=200),
    ]
    assert cp.conversion_factor(rows) == 100


def test_conversion_factor_is_none_on_empty_input():
    assert cp.conversion_factor([]) is None


def test_conversion_factor_is_none_when_nothing_is_matched():
    rows = [_row(oraculo_points=None, matched=False, jp_sf=100)]
    assert cp.conversion_factor(rows) is None


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


# --- global_conversion_factor: k over the whole population, not a table ----


def test_global_conversion_factor_is_the_same_regardless_of_which_subset_asks():
    """The whole point of computing `k` once per request: a caller passing
    the full player population must get the population's median ratio, not
    something a smaller table would have derived on its own."""
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
    # ratios: 100, 100, 25 -> median 100, same figure `conversion_factor`
    # reaches directly over the equivalent rows in
    # `test_conversion_factor_is_the_median_ratio_over_matched_rows`.
    k = cp.global_conversion_factor(biwenger_players, jp_index, oraculo_index)
    assert k == 100


def test_global_conversion_factor_is_none_with_no_oraculo_data():
    biwenger_players = {1: {"id": 1, "name": "A", "position": 3, "price": 1}}
    jp_index = build_jp_index([{"name": "A", "slug": "a"}])
    assert cp.global_conversion_factor(biwenger_players, jp_index, {}) is None
