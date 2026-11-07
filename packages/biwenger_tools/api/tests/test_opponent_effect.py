"""Tests for `logic/opponent_effect.py`.

The question is whether a defender facing Barcelona or Real Madrid scores
below what he usually scores. Every assertion compares a player with
himself, so a weak defender is never mistaken for a bad fixture.
"""

from packages.biwenger_tools.api.logic import opponent_effect as oe
from packages.biwenger_tools.api.logic.lineup import DEF, GK, MID


def _report(pid, name, position, points):
    return {
        "player": {"id": pid, "name": name, "position": position},
        "points": points,
    }


def _game(game_id, home, away, home_reports=(), away_reports=(), status="finished"):
    return {
        "id": game_id,
        "status": status,
        "home": {"name": home, "reports": list(home_reports)},
        "away": {"name": away, "reports": list(away_reports)},
    }


def _round(round_id, name, *games):
    return {"id": round_id, "name": name, "games": list(games)}


def _defender_season(points_by_opponent: dict, pid=1, name="Tenaglia"):
    """One defender of Alavés, one round per opponent, in the given order."""
    return [
        _round(
            100 + i,
            f"Jornada {i + 1}",
            _game(500 + i, "Alavés", opp, home_reports=[_report(pid, name, DEF, pts)]),
        )
        for i, (opp, pts) in enumerate(points_by_opponent.items())
    ]


# ---------------------------------------------------------------------------
# appearances
# ---------------------------------------------------------------------------


def test_each_side_of_a_game_faces_the_other():
    rounds = [
        _round(
            1,
            "Jornada 1",
            _game(
                10,
                "Alavés",
                "Barcelona",
                home_reports=[_report(1, "Tenaglia", DEF, -7)],
                away_reports=[_report(2, "Joan García", GK, 4)],
            ),
        )
    ]
    apps = {a.player_id: a for a in oe.appearances(rounds)}
    assert (apps[1].team, apps[1].opponent, apps[1].home) == (
        "Alavés",
        "Barcelona",
        True,
    )
    assert (apps[2].team, apps[2].opponent, apps[2].home) == (
        "Barcelona",
        "Alavés",
        False,
    )
    assert apps[1].round_id == 1 and apps[1].points == -7


def test_a_game_listed_under_two_round_ids_counts_once():
    """Biwenger lists a postponed matchday's games under the original round
    and again under each "aplazada" id. Counting both would weigh the
    postponed games double."""
    game = _game(10, "Racing", "Barcelona", [_report(1, "Mantilla", DEF, -5)])
    rounds = [
        _round(4904, "Jornada 6", game),
        _round(5125, "Jornada 6 (aplazada)", game),
        _round(5176, "Jornada 6 (aplazada)", game),
    ]
    assert len(oe.appearances(rounds)) == 1


def test_an_unfinished_game_and_a_report_without_points_are_left_out():
    rounds = [
        _round(
            1,
            "Jornada 1",
            _game(10, "A", "B", [_report(1, "X", DEF, 3)], status="preview"),
            _game(11, "C", "D", [{"player": {"id": 2, "name": "Y", "position": 2}}]),
        )
    ]
    assert oe.appearances(rounds) == []


# ---------------------------------------------------------------------------
# opponent_deltas
# ---------------------------------------------------------------------------


def test_a_delta_is_against_the_players_own_mean_elsewhere():
    rounds = _defender_season({"Getafe": 4, "Elche": 6, "Celta": 5, "Barcelona": -7})
    deltas = oe.opponent_deltas(oe.appearances(rounds), "Barcelona", {DEF})
    assert [round(d, 2) for d, _ in deltas] == [-12.0]


def test_the_baseline_leaves_out_every_watched_opponent():
    """A bad afternoon against Madrid must not lower the bar the Barcelona
    game is measured against."""
    rounds = _defender_season(
        {"Getafe": 4, "Elche": 6, "Celta": 5, "Real Madrid": -10, "Barcelona": -7}
    )
    deltas = oe.opponent_deltas(oe.appearances(rounds), "Barcelona", {DEF})
    assert [round(d, 2) for d, _ in deltas] == [-12.0]


def test_a_player_with_too_few_other_games_has_no_baseline():
    rounds = _defender_season({"Getafe": 4, "Elche": 6, "Barcelona": -7})
    assert oe.opponent_deltas(oe.appearances(rounds), "Barcelona", {DEF}) == []


def test_only_the_asked_positions_are_measured():
    rounds = _defender_season({"Getafe": 4, "Elche": 6, "Celta": 5, "Barcelona": -7})
    assert oe.opponent_deltas(oe.appearances(rounds), "Barcelona", {GK, MID}) == []


# ---------------------------------------------------------------------------
# summarize / by_match
# ---------------------------------------------------------------------------


def test_summary_counts_how_many_fell_below_their_own_mean():
    deltas = [(-4.0, None), (-2.0, None), (1.0, None)]
    summary = oe.summarize(deltas)
    assert summary == {"n": 3, "mean": -5 / 3, "median": -2.0, "below": 2}


def test_an_empty_sample_has_no_summary():
    assert oe.summarize([]) is None


def test_by_match_groups_one_teams_defence_in_one_game():
    """Appearances in one game are not independent: one 6–1 sinks the whole
    back line. The per-match view is the honest count."""
    a = oe.Appearance(1, "A", DEF, "Alavés", "Barcelona", False, -7, 9, "J11", 50)
    b = oe.Appearance(2, "B", DEF, "Alavés", "Barcelona", False, -5, 9, "J11", 50)
    c = oe.Appearance(3, "C", DEF, "Betis", "Barcelona", True, 6, 8, "J9", 51)
    matches = oe.by_match([(-6.0, a), (-4.0, b), (2.0, c)])
    assert matches == [
        {"round_name": "J11", "team": "Alavés", "home": False, "n": 2, "mean": -5.0},
        {"round_name": "J9", "team": "Betis", "home": True, "n": 1, "mean": 2.0},
    ]


# ---------------------------------------------------------------------------
# jp_vs_real
# ---------------------------------------------------------------------------


def test_jp_and_real_deltas_are_measured_on_the_same_rounds():
    """Whether Jornada Perfecta already prices the fixture in: its projection
    against the player's own usual projection, beside the same for the
    points he actually scored."""
    rounds = _defender_season({"Getafe": 4, "Elche": 6, "Celta": 5, "Barcelona": -7})
    league_jp = {100: {"1": 400}, 101: {"1": 420}, 102: {"1": 410}, 103: {"1": 440}}
    rows = oe.jp_vs_real(oe.appearances(rounds), league_jp, "Barcelona", {DEF})
    assert len(rows) == 1
    jp_delta, real_delta, app = rows[0]
    assert (jp_delta, real_delta, app.points) == (30.0, -12.0, -7)


def test_a_round_without_a_league_jp_capture_is_not_used():
    rounds = _defender_season({"Getafe": 4, "Elche": 6, "Celta": 5, "Barcelona": -7})
    league_jp = {100: {"1": 400}, 101: {"1": 420}, 103: {"1": 440}}
    assert oe.jp_vs_real(oe.appearances(rounds), league_jp, "Barcelona", {DEF}) == []
