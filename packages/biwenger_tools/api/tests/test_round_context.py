"""Tests for reading where the season is.

The payload shapes are the ones `cf.biwenger.com/rounds/la-liga` really
returned on 2026-08-29, not invented: Jornada 3 active with two of ten games
played, and a `next` pointing at Jornada 6.
"""

from datetime import datetime, timedelta

import pytest

from core.constants import MADRID_TZ
from packages.biwenger_tools.api.logic import round_context

# 2026-09-03 21:00 Madrid — the kickoff the live probe returned.
KICKOFF = int(datetime(2026, 9, 3, 21, 0, tzinfo=MADRID_TZ).timestamp())


def _payload(played=2, total=10, next_games=((KICKOFF,),)):
    games = [{"status": "finished" if i < played else "preview"} for i in range(total)]
    return {
        "id": 4901,
        "name": "Jornada 3",
        "status": "active",
        "games": games,
        "next": {
            "id": 4904,
            "name": "Jornada 6",
            "games": [{"date": d[0]} for d in next_games],
        },
    }


def test_an_open_round_is_read_from_its_games_not_assumed():
    """The reglamento's *jornada única* (2.5.8) says a round is not final
    until every match is played. The platform infers that from Jornada
    Perfecta; here Biwenger states it."""
    context = round_context.read(_payload(played=2, total=10))

    assert context.name == "Jornada 3"
    assert context.is_open
    assert (context.played, context.total) == (2, 10)


def test_a_finished_round_is_not_open():
    context = round_context.read(_payload(played=10, total=10))

    assert not context.is_open


def test_the_next_round_is_not_the_next_number():
    """2026/27 interleaves postponed rounds: with Jornada 3 active the next
    round to be played is **Jornada 6**, and Jornada 4 comes after it.

    Anything deriving "the next matchday" from the round number, or from the
    order of `season.rounds[]`, gets this wrong — the array had Jornada 6
    before Jornada 4. Biwenger's own `next` is the only reliable answer.
    """
    context = round_context.read(_payload())

    assert context.next_name == "Jornada 6"


def test_the_clause_deadline_is_a_day_before_the_first_kickoff():
    """Biwenger freezes clauses 24 h before a matchday's first match. Cash has
    to be positive *before* that, not during the round — a deadline nothing in
    the code knew about."""
    context = round_context.read(_payload())

    assert context.next_kickoff == datetime(2026, 9, 3, 21, 0, tzinfo=MADRID_TZ)
    assert context.clause_deadline == datetime(2026, 9, 2, 21, 0, tzinfo=MADRID_TZ)


def test_the_earliest_kickoff_wins_when_the_round_has_several():
    """A round's games are not in time order, and the freeze keys on the
    first one."""
    later = KICKOFF + int(timedelta(days=2).total_seconds())
    context = round_context.read(_payload(next_games=((later,), (KICKOFF,))))

    assert context.next_kickoff == datetime(2026, 9, 3, 21, 0, tzinfo=MADRID_TZ)


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"name": "Jornada 3"}, {"games": None, "next": None}, "not a dict"],
)
def test_a_partial_payload_yields_an_empty_context_not_a_crash(payload):
    """This decorates a message. Losing the lineup because the calendar could
    not be read would be the wrong trade."""
    context = round_context.read(payload)

    assert context.clause_deadline is None or context.next_kickoff is not None


def test_no_context_renders_no_line():
    """Better a message without the header than a header saying nothing."""
    assert round_context.format_line(round_context.RoundContext()) == ""


def test_the_line_names_the_round_the_next_one_and_the_freeze():
    line = round_context.format_line(round_context.read(_payload()))

    assert "Jornada 3" in line and "2/10" in line and "en juego" in line
    assert "Jornada 6" in line
    assert "03/09 21:00" in line
    assert "02/09 21:00" in line, "el corte de cláusulas, 24 h antes"
