"""Unit tests for the Oráculo join in `api/logic/rows.py`.

The row already carries Biwenger and Jornada Perfecta. This adds a third
source, and every test here is about the ways a third source can quietly
poison a decision rather than about the happy path.
"""

from packages.biwenger_tools.api.logic import custom_prediction as cp
from packages.biwenger_tools.api.logic import rows as rows_mod
from packages.biwenger_tools.api.logic.player_matching import build_jp_index

_SCALE = cp.ProjectionScale(oraculo=(0.0, 10.0), jp=(0.0, 1_000.0))


def _bw(bw_id, name, position=3, price=1_000_000):
    return {"id": bw_id, "name": name, "position": position, "price": price}


def _oraculo(name, slug, points, chance=70):
    return {
        "playerName": name,
        "slug": slug,
        "predictedPoints": points,
        "chance": chance,
    }


def _index(entries):
    return rows_mod.build_oraculo_index(entries)


# --- the join itself -------------------------------------------------------


def test_a_matched_player_carries_the_oraculo_numbers():
    index = _index([_oraculo("Pedri", "pedri-1", 5.4, 80)])
    row = rows_mod.build_row(_bw(1, "Pedri"), build_jp_index([]), index)
    assert row["oraculo_points"] == 5.4
    assert row["oraculo_chance"] == 80
    assert row["oraculo_matched"] is True


def test_an_unmatched_player_is_marked_not_zeroed():
    """`sf_of` returning 0 for a player JP does not carry once took the league
    ranking down. A second source must not repeat it: "no opinion" and "bad"
    are different states and only one of them should move a projection."""
    row = rows_mod.build_row(_bw(1, "Nadie"), build_jp_index([]), _index([]))
    assert row["oraculo_matched"] is False
    assert row["oraculo_points"] is None
    assert row["oraculo_chance"] is None


def test_a_zero_projection_is_an_opinion_not_a_gap():
    """The site prints `Esperado 0.00` for a player it expects not to play.
    That is an answer, and it must not read as "not carried"."""
    index = _index([_oraculo("Suplente", "suplente-9", 0.0, 10)])
    row = rows_mod.build_row(_bw(9, "Suplente"), build_jp_index([]), index)
    assert row["oraculo_matched"] is True
    assert row["oraculo_points"] == 0.0


def test_no_oraculo_index_leaves_the_row_untouched():
    """Every existing caller passes two arguments. The third is optional so
    the join lands without a flag day, and a row built without it must look
    exactly as it does today."""
    row = rows_mod.build_row(_bw(1, "Pedri"), build_jp_index([]))
    assert row["oraculo_matched"] is False
    assert "jp_player" in row


# --- the lists -------------------------------------------------------------


def test_the_lists_a_player_appears_on_ride_along():
    index = rows_mod.build_oraculo_index(
        [_oraculo("Pedri", "pedri-1", 5.4)],
        lists={"goleadores": ["pedri-1"], "chollos": ["otro-2"]},
    )
    row = rows_mod.build_row(_bw(1, "Pedri"), build_jp_index([]), index)
    assert row["oraculo_lists"] == ["goleadores"]


def test_a_player_on_no_list_gets_an_empty_list_not_none():
    """An empty list is "checked, not on any", which is the normal state of
    92% of players. `None` would read as "never looked"."""
    index = _index([_oraculo("Pedri", "pedri-1", 5.4)])
    row = rows_mod.build_row(_bw(1, "Pedri"), build_jp_index([]), index)
    assert row["oraculo_lists"] == []


def test_lists_are_sorted_so_the_stars_are_stable():
    index = rows_mod.build_oraculo_index(
        [_oraculo("Pedri", "pedri-1", 5.4)],
        lists={"goleadores": ["pedri-1"], "asistentes": ["pedri-1"]},
    )
    row = rows_mod.build_row(_bw(1, "Pedri"), build_jp_index([]), index)
    assert row["oraculo_lists"] == ["asistentes", "goleadores"]


# --- coverage, which decides whether the blend runs at all -----------------


def test_coverage_counts_rows_with_an_opinion():
    index = _index([_oraculo("A", "a-1", 4.0), _oraculo("B", "b-2", 3.0)])
    jp = build_jp_index([])
    built = [
        rows_mod.build_row(_bw(1, "A"), jp, index),
        rows_mod.build_row(_bw(2, "B"), jp, index),
        rows_mod.build_row(_bw(3, "C"), jp, index),
        rows_mod.build_row(_bw(4, "D"), jp, index),
    ]
    assert rows_mod.oraculo_coverage(built) == 0.5


def test_coverage_of_nothing_is_zero_not_a_crash():
    assert rows_mod.oraculo_coverage([]) == 0.0


# --- the row builders forward the index -------------------------------------


def test_build_squad_rows_forwards_the_oraculo_index():
    index = _index([_oraculo("Pedri", "pedri-1", 5.4)])
    squad = [{"id": 1, "owner": {}}]
    rows = rows_mod.build_squad_rows(
        squad, {1: _bw(1, "Pedri")}, build_jp_index([]), index
    )
    assert rows[0]["oraculo_matched"] is True


def test_build_squad_rows_with_no_index_matches_nothing():
    """Every existing caller omits the index; nothing must break for them."""
    squad = [{"id": 1, "owner": {}}]
    rows = rows_mod.build_squad_rows(squad, {1: _bw(1, "Pedri")}, build_jp_index([]))
    assert rows[0]["oraculo_matched"] is False


def test_build_market_rows_forwards_the_oraculo_index():
    index = _index([_oraculo("Pedri", "pedri-1", 5.4)])
    sale = {"player": {"id": 1}}
    rows = rows_mod.build_market_rows(
        [sale], {1: _bw(1, "Pedri")}, build_jp_index([]), index
    )
    assert rows[0]["oraculo_matched"] is True


# --- the blend: k is a global input, never recomputed per table ------------


def _jp_with_rate(name, slug, rate):
    return {"name": name, "slug": slug, "predict": [{"type": 2, "rate": rate}]}


def test_the_same_player_gets_the_same_projection_in_two_different_tables():
    """The defect this closes: the scale used to be derived from whichever
    rows a given photo happened to render, so the same player could blend to
    three different numbers depending on who shared his table. The scale is
    now an input the caller supplies once per request — passing the same
    scale into two disjoint row-sets must land the shared player on the same
    number."""
    index = _index(
        [
            _oraculo("A", "a-1", 4.0),
            _oraculo("B", "b-2", 3.0),
            _oraculo("C", "c-3", 5.0),
        ]
    )
    jp = build_jp_index(
        [
            _jp_with_rate("A", "a", 430),
            _jp_with_rate("B", "b", 300),
            _jp_with_rate("C", "c", 500),
        ]
    )
    biwenger_players = {1: _bw(1, "A"), 2: _bw(2, "B"), 3: _bw(3, "C")}

    rows_with_b = rows_mod.build_squad_rows(
        [{"id": 1, "owner": {}}, {"id": 2, "owner": {}}],
        biwenger_players,
        jp,
        index,
        oraculo_scale=_SCALE,
    )
    rows_with_c = rows_mod.build_squad_rows(
        [{"id": 1, "owner": {}}, {"id": 3, "owner": {}}],
        biwenger_players,
        jp,
        index,
        oraculo_scale=_SCALE,
    )

    a_with_b = next(r for r in rows_with_b if r["name"] == "A")
    a_with_c = next(r for r in rows_with_c if r["name"] == "A")
    assert a_with_b["custom_prediction"] is not None
    assert a_with_b["custom_prediction"] == a_with_c["custom_prediction"]


def test_no_scale_leaves_the_row_with_no_custom_prediction_key():
    """Every existing caller omits `oraculo_scale`. Nothing must break for
    them, and nothing must silently blend without a scale to convert
    Oráculo's range."""
    index = _index([_oraculo("Pedri", "pedri-1", 5.4)])
    squad = [{"id": 1, "owner": {}}]
    rows = rows_mod.build_squad_rows(
        squad, {1: _bw(1, "Pedri")}, build_jp_index([]), index
    )
    assert "custom_prediction" not in rows[0]


def test_low_coverage_still_skips_the_blend_even_with_a_scale():
    """A scale alone is not enough — a read where Oráculo covers too few of
    these exact players must not blend, per `ORACULO_MIN_COVERAGE`."""
    index = _index([_oraculo("A", "a-1", 4.0)])
    jp = build_jp_index([_jp_with_rate("A", "a", 430), _jp_with_rate("B", "b", 300)])
    biwenger_players = {1: _bw(1, "A"), 2: _bw(2, "B")}
    squad = [{"id": 1, "owner": {}}, {"id": 2, "owner": {}}]
    rows = rows_mod.build_squad_rows(
        squad, biwenger_players, jp, index, oraculo_scale=_SCALE
    )
    a_row = next(r for r in rows if r["name"] == "A")
    assert a_row["custom_prediction"] == 430
