"""Tests for `sf_of` — the shared SF reader used to rank, filter and price
rival clausulazo candidates."""

from packages.biwenger_tools.api.logic.clausulazo_candidates import sf_of


def _jp(rate):
    return {"predict": [{"type": 2, "rate": rate}]}


def test_sf_of_prefers_the_blended_prediction_over_the_raw_jp_rate():
    """`sf_of` feeds ranking, affordability and pricing for clausulazo
    candidates. If it read the raw JP rate while the row displays the
    Oráculo blend, a candidate could be ranked, filtered or priced by a
    number nobody sees on the card — the same bug the photo table had."""
    row = {"jp_player": _jp(100), "custom_prediction": 250}
    assert sf_of(row) == 250


def test_sf_of_falls_back_to_the_raw_jp_rate_when_no_blend_ran():
    row = {"jp_player": _jp(180)}
    assert sf_of(row) == 180


def test_sf_of_is_zero_for_a_player_with_no_projection_at_all():
    assert sf_of({"jp_player": None}) == 0
    assert sf_of({}) == 0
