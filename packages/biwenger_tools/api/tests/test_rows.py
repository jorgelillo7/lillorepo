"""Unit tests for the Oráculo join in `api/logic/rows.py`.

The row already carries Biwenger and Jornada Perfecta. This adds a third
source, and every test here is about the ways a third source can quietly
poison a decision rather than about the happy path.
"""

from packages.biwenger_tools.api.logic import rows as rows_mod
from packages.biwenger_tools.api.logic.player_matching import build_jp_index


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
