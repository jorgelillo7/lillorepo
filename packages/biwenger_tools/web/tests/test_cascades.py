"""Clausulazo cascades: the days most of the league claused each other.

Spec: `openspec/specs/biwenger_tools/web-dataviz/spec.md`, "Clausulazo
cascades get a table of their own on /mercado".
"""

from datetime import date

from core.domain.models import Clausulazo
from packages.biwenger_tools.cascades import find_cascades

TEAMS = ["A", "B", "C", "D", "E", "F", "G"]


def _c(fecha, seller, buyer, price=1_000_000, player="P", anulado=None):
    return Clausulazo(fecha, player, seller, buyer, price, anulado=anulado)


def _round_robin(day="26-11-2026", hour=19, teams=TEAMS, n=5):
    """`n` clausulazos a minute apart, each team clausing the next one."""
    return [
        _c(f"{day} {hour}:{i:02d}", teams[(i + 1) % len(teams)], teams[i % len(teams)])
        for i in range(n)
    ]


def _season_teams():
    """One clausulazo touching every team, weeks earlier, so the season counts
    seven active managers."""
    return [
        _c("01-09-2026 10:00", "A", "B"),
        _c("01-09-2026 12:00", "C", "D"),
        _c("02-09-2026 10:00", "E", "F"),
        _c("03-09-2026 10:00", "G", "A"),
    ]


def test_a_cascade_is_five_clausulazos_in_a_day_involving_all_but_two():
    night = _round_robin(n=5)  # A..F: six of seven teams
    cascades = find_cascades(_season_teams() + night)

    assert len(cascades) == 1
    cascade = cascades[0]
    assert cascade.day == date(2026, 11, 26)
    assert (cascade.count, cascade.involved, cascade.active) == (5, 6, 7)
    assert (cascade.first, cascade.last) == ("19:00", "19:04")


def test_five_clausulazos_among_few_managers_are_not_a_cascade():
    night = _round_robin(teams=["A", "B", "C", "D"], n=6)  # four of seven

    assert find_cascades(_season_teams() + night) == []


def test_a_cascade_day_runs_from_six_in_the_morning_to_six_the_next():
    late = _round_robin(day="26-11-2026", hour=23, n=3)
    after_midnight = [
        _c("27-11-2026 00:05", "E", "D"),
        _c("27-11-2026 05:59", "F", "E"),
    ]
    next_morning = _c("27-11-2026 06:00", "G", "F")

    cascades = find_cascades(_season_teams() + late + after_midnight + [next_morning])

    assert len(cascades) == 1
    assert cascades[0].day == date(2026, 11, 26)
    assert cascades[0].count == 5
    assert cascades[0].last == "05:59"


def test_a_season_s_cascades_come_from_its_own_clausulazos_only():
    this_season = _season_teams() + _round_robin(n=3)
    last_season = _round_robin(day="26-11-2025", n=5)

    assert find_cascades(this_season) == []
    assert [c.day for c in find_cascades(_season_teams() + last_season)] == [
        date(2025, 11, 26)
    ]


def test_responses_are_clausulazos_by_a_team_already_hit_that_day():
    night = [
        _c("26-11-2026 19:00", "B", "A"),  # A starts
        _c("26-11-2026 19:00", "C", "B"),  # B hit the same minute: a response
        _c("26-11-2026 19:10", "D", "E"),  # E not hit: not a response
        _c("26-11-2026 19:20", "E", "D"),  # D hit at 19:10: a response
        _c("26-11-2026 19:30", "F", "C"),  # C hit at 19:00: a response
    ]

    assert find_cascades(_season_teams() + night)[0].responses == 3


def test_who_started_paid_most_and_was_hit_most():
    night = [
        _c("26-11-2026 18:54", "B", "A", 14_000_000, "Grimaldo"),
        _c("26-11-2026 18:54", "C", "B", 11_000_000, "Gerard Martín"),
        _c("26-11-2026 19:15", "D", "E", 45_000_000, "Mbappé"),
        _c("26-11-2026 19:20", "B", "F", 5_000_000),
        _c("26-11-2026 19:25", "B", "E", 10_000_000),
    ]

    cascade = find_cascades(_season_teams() + night)[0]

    assert {
        (s.equipo_comprador, s.jugador, s.equipo_vendedor) for s in cascade.starters
    } == {
        ("A", "Grimaldo", "B"),
        ("B", "Gerard Martín", "C"),
    }
    assert (cascade.top_payer, cascade.top_paid, cascade.top_paid_count) == (
        "E",
        55_000_000,
        2,
    )
    assert (cascade.most_hit, cascade.hits) == ("B", 3)
    assert cascade.total == 85_000_000
    # The store keeps no order inside a minute: the first two in either order.
    players = [c.jugador for c in cascade.baile]
    assert set(players[:2]) == {"Grimaldo", "Gerard Martín"}
    assert players[2:] == ["Mbappé", "P", "P"]


def test_a_cancelled_clausulazo_is_left_out_of_a_cascade():
    night = _round_robin(n=5)
    night.append(
        _c("26-11-2026 19:30", "G", "F", 99_000_000, "Courtois", "único portero")
    )

    cascade = find_cascades(_season_teams() + night)[0]

    assert cascade.count == 5
    assert "Courtois" not in [c.jugador for c in cascade.baile]
    assert cascade.total == 5_000_000


def test_with_the_board_order_stored_one_team_started_it():
    """The scraper stores each clausulazo's second and place in its board entry:
    with them, the first minute has one starter, and a clausulazo made before
    its buyer was hit is no response."""
    night = [
        Clausulazo(
            "26-11-2026 18:54",
            "Gerard Martín",
            "C",
            "B",
            11_000_000,
            segundos=1795715683,
            orden=1,
        ),
        Clausulazo(
            "26-11-2026 18:54",
            "Grimaldo",
            "B",
            "A",
            14_000_000,
            segundos=1795715683,
            orden=0,
        ),
        *_round_robin(hour=20, teams=["D", "E", "F", "A"], n=3),
    ]

    cascade = find_cascades(_season_teams() + night)[0]

    assert [(s.equipo_comprador, s.jugador) for s in cascade.starters] == [
        ("A", "Grimaldo")
    ]
    assert [c.jugador for c in cascade.baile][:2] == ["Grimaldo", "Gerard Martín"]
    # B after Grimaldo, E at 20:01 after 20:00, F at 20:02 after 20:01.
    assert cascade.responses == 3
