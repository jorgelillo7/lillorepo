"""Tests for `logic/kickoff_lineup.py`.

Biwenger freezes the whole eleven at the matchday's first kick-off
(`lineupRoundChanges = 0`). The tick asks every quarter of an hour whether
that kick-off is half an hour away, and only then is the lineup set.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from core.constants import MADRID_TZ
from packages.biwenger_tools.api.logic import actions
from packages.biwenger_tools.api.logic import kickoff_lineup as kl

KICKOFF = datetime(2026, 11, 20, 21, 0, tzinfo=MADRID_TZ)


def _games(*kickoffs: datetime) -> list:
    return [{"status": "pending", "date": int(k.timestamp())} for k in kickoffs]


def _upcoming(first: datetime = KICKOFF) -> dict:
    """The current round not started yet, its first match at `first`."""
    return {"id": 4911, "games": _games(first + timedelta(days=1), first)}


def test_the_tick_half_an_hour_before_the_first_kickoff_is_due():
    assert kl.due(_upcoming(), KICKOFF - timedelta(minutes=30)) == 4911


def test_exactly_one_quarter_hour_tick_falls_in_the_window():
    """Ticks every 15 minutes: one, and only one, sets the lineup."""
    ticks = [KICKOFF - timedelta(minutes=m) for m in range(0, 120, 15)]

    due = [t for t in ticks if kl.due(_upcoming(), t) is not None]

    assert due == [KICKOFF - timedelta(minutes=30)]


def test_a_kickoff_off_the_quarter_hour_still_gets_exactly_one_tick():
    kickoff = KICKOFF + timedelta(minutes=5)
    ticks = [KICKOFF - timedelta(minutes=m) for m in range(-15, 120, 15)]

    due = [t for t in ticks if kl.due(_upcoming(kickoff), t) is not None]

    assert due == [KICKOFF - timedelta(minutes=15)]


def test_a_round_under_way_points_at_the_next_one():
    """Mid-matchday the current round has kicked off; the lineup that can
    still change is the next round's, before its own first match."""
    round_data = {
        "id": 4910,
        "games": [{"status": "finished", "date": int(KICKOFF.timestamp()) - 86400}],
        "next": {"id": 4911, "games": _games(KICKOFF)},
    }

    assert kl.due(round_data, KICKOFF - timedelta(minutes=30)) == 4911


def test_a_moved_match_moves_the_tick():
    """The first kick-off is read live: a match brought forward a day is the
    one the lineup is set before."""
    earlier = KICKOFF - timedelta(days=1)

    assert kl.due(_upcoming(earlier), earlier - timedelta(minutes=30)) == 4911
    assert kl.due(_upcoming(earlier), KICKOFF - timedelta(minutes=30)) is None


def test_far_from_any_kickoff_nothing_is_due():
    assert kl.due(_upcoming(), KICKOFF - timedelta(hours=5)) is None


def test_an_unreadable_round_is_never_due():
    assert kl.due({}, KICKOFF) is None
    assert kl.due({"id": 4911, "games": []}, KICKOFF) is None


# ---------------------------------------------------------------------------
# run_kickoff_lineup (service)
# ---------------------------------------------------------------------------


def test_a_tick_that_is_not_due_logs_in_to_nothing():
    """Most ticks only read the fixtures: no session, no lineup."""
    with (
        patch.object(actions, "fetch_round", return_value=_upcoming()),
        patch.object(actions, "run_auto_pick_lineup") as pick,
        patch.object(actions, "build_context") as context,
    ):
        result = actions.run_kickoff_lineup(now=KICKOFF - timedelta(hours=3))

    assert result == {"due": False}
    pick.assert_not_called()
    context.assert_not_called()


def test_the_due_tick_sets_the_lineup():
    with (
        patch.object(actions, "fetch_round", return_value=_upcoming()),
        patch.object(
            actions, "run_auto_pick_lineup", return_value={"applied": True}
        ) as pick,
    ):
        result = actions.run_kickoff_lineup(now=KICKOFF - timedelta(minutes=30))

    pick.assert_called_once_with()
    assert result == {"due": True, "round_id": 4911, "applied": True}
