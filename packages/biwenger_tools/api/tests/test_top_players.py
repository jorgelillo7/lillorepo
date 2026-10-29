"""Unit tests for `api/logic/top_players` — the five best of every squad."""

from packages.biwenger_tools.api.logic import top_players


def _row(name, score, team=1):
    return {"name": name, "team_id": team, "custom_prediction": score}


def test_top_ranks_each_squad_by_its_shown_projection():
    scores = [300, 900, 500, 700, 100, 600]
    rows = [_row(f"P{i}", score) for i, score in enumerate(scores)]
    names = [r["name"] for r in top_players.best(rows, 5)]
    assert names == ["P1", "P3", "P5", "P2", "P0"]


def test_top_rows_carry_manager_and_club_in_manager_order():
    blocks = [("Lucena", [_row("Raphinha", 1111, team=3)]), ("Manu", [_row("X", 900)])]
    rows = top_players.rows_for_image(blocks, {3: "Barcelona"})
    assert [(r["Mánager"], r["Equipo"], r["name"]) for r in rows] == [
        ("Lucena", "Barcelona", "Raphinha"),
        ("Manu", "—", "X"),
    ]


def test_a_protected_player_is_not_worth_reading_yet():
    import time

    assert top_players.locked({"clause_locked_until": time.time() + 86_400})
    assert not top_players.locked({"clause_locked_until": time.time() - 1})
    assert not top_players.locked({"clause_locked_until": None})
