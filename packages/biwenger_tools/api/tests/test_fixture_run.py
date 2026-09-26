"""Tests for the next-fixtures difficulty shown in the market images.

Payload shapes follow `cf.biwenger.com/rounds/la-liga/{id}`: each game has a
`date`, a `status`, and per side the team `id` and — only while the game is
pending — `difficulty.rating`, the difficulty *that side faces* (Barcelona at
home to Getafe read 25, Getafe 94).
Spec: `openspec/specs/biwenger_tools/team-analysis/spec.md`.
"""

from packages.biwenger_tools.api.logic import fixture_run

NOW = 1_790_000_000
DAY = 86_400


def _game(home, away, day, home_rating=None, away_rating=None, status="pending"):
    def side(team, rating):
        out = {"id": team}
        if rating is not None:
            out["difficulty"] = {"rating": rating}
        return out

    return {
        "date": NOW + day * DAY,
        "status": status,
        "home": side(home, home_rating),
        "away": side(away, away_rating),
    }


def _round(*games, round_id=1, status="pending"):
    return {"id": round_id, "status": status, "games": list(games)}


def test_upcoming_orders_each_team_by_kickoff_not_by_round():
    """A postponed round is listed after later ones; the date decides."""
    later = _round(_game(3, 4, 14, 60, 40), round_id=9)
    postponed = _round(_game(3, 5, 2, 20, 80), round_id=6)
    upcoming = fixture_run.upcoming_by_team([later, postponed], NOW)
    assert fixture_run.next_ratings(upcoming, 3, 5) == [20, 60]


def test_played_and_unrated_games_are_left_out():
    rounds = [
        _round(
            _game(3, 4, -1, 10, 90, status="finished"),
            _game(3, 5, 3),  # pending but no difficulty published
            _game(3, 6, 5, 70, 30),
        )
    ]
    upcoming = fixture_run.upcoming_by_team(rounds, NOW)
    assert fixture_run.next_ratings(upcoming, 3, 5) == [70]
    assert fixture_run.next_ratings(upcoming, 6, 5) == [30]


def test_next_ratings_stops_at_n():
    rounds = [_round(*[_game(3, 10 + i, i + 1, 50 + i, 50) for i in range(8)])]
    upcoming = fixture_run.upcoming_by_team(rounds, NOW)
    assert fixture_run.next_ratings(upcoming, 3, 5) == [50, 51, 52, 53, 54]


def test_label_bands_the_average():
    assert fixture_run.label([20, 40]) == "fácil 30"
    assert fixture_run.label([44, 44]) == "fácil 44"
    assert fixture_run.label([45, 45]) == "medio 45"
    assert fixture_run.label([40, 60]) == "medio 50"
    assert fixture_run.label([55, 55]) == "medio 55"
    assert fixture_run.label([56, 56]) == "difícil 56"
    assert fixture_run.label([61, 80]) == "difícil 71"
    assert fixture_run.label([]) == "—"


def test_rounds_to_read_takes_open_rounds_in_the_listed_order():
    current = {
        "id": 4905,
        "season": {
            "rounds": [
                {"id": 4904, "status": "finished"},
                {"id": 4905, "status": "active"},
                {"id": 4906, "status": "pending"},
                {"id": 5176, "status": "pending"},
            ]
        },
    }
    assert fixture_run.rounds_to_read(current) == [4905, 4906, 5176]


def test_annotate_names_the_column_and_marks_each_row():
    upcoming = fixture_run.upcoming_by_team([_round(_game(3, 4, 1, 20, 80))], NOW)
    rows = [{"team_id": 3}, {"team_id": 4}, {"team_id": None}]
    column = fixture_run.annotate(rows, upcoming, 5)
    assert column == "Calendario (5)"
    assert [r[column] for r in rows] == ["fácil 20", "difícil 80", "—"]


def test_annotate_says_so_when_the_calendar_could_not_be_read():
    """A failed read must not look like "no upcoming games" (LP-11)."""
    rows = [{"team_id": 3}]
    column = fixture_run.annotate(rows, None, 5)
    assert column == "Calendario (sin datos)"
    assert rows[0][column] == "—"
