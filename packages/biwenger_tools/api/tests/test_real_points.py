"""Tests for `logic/real_points.py`.

`personalizado()` moved here from the draft skill's `fetch_real_points.py`
(still imported from there, unchanged) so the grading script can reuse it
without importing a skill script. `reports_for_round` is new: the moved
function sums over whatever reports it is handed, and grading one matchday
needs exactly one of them isolated first.
"""

from packages.biwenger_tools.api.logic import real_points
from packages.biwenger_tools.api.logic.real_points import (
    DEF,
    GK,
    personalizado,
    reports_for_round,
)


def _report(round_id: int, **rawstats):
    return {
        "match": {"round": {"id": round_id, "name": f"Round {round_id}"}},
        "rawStats": {"minutesPlayed": 90, **rawstats},
    }


def test_reports_for_round_keeps_only_the_matching_matchday():
    """A player's season history spans every round; grading one matchday
    must not silently sum the other 37."""
    reports = [_report(4899, score2=3), _report(4901, score2=10)]

    selected = reports_for_round(reports, 4901)

    assert selected == [_report(4901, score2=10)]


def test_reports_for_round_is_empty_when_the_player_did_not_feature():
    reports = [_report(4899, score2=3)]

    assert reports_for_round(reports, 4901) == []


def test_reports_for_round_tolerates_a_report_with_no_round_at_all():
    """A malformed or preview report (no `match.round`) must not raise —
    it simply cannot belong to the round being graded."""
    reports = [{"rawStats": {"minutesPlayed": 90}}]

    assert reports_for_round(reports, 4901) == []


def test_personalizado_still_lives_here_and_still_scores_a_clean_sheet():
    """Relocated, not rewritten: the keeper/defender clean-sheet split this
    league pays for is the same behaviour, just imported from its new home."""
    keeper = personalizado([_report(1, cleanSheet=True, score2=6)], GK)
    defender = personalizado([_report(1, cleanSheet=True, score2=6)], DEF)

    assert keeper["points"] - defender["points"] == 1


# --- a silent zero is how eight rounds reported nothing ---------------------


def test_a_fielded_player_with_no_report_is_not_a_zero():
    """`personalizado` sums whatever it is handed, so an empty list scores 0 —
    the same number as a player who turned out badly. A whole backfill once
    printed `0 pts reales` for eight rounds because the field selector had
    gone stale upstream and every report came back empty, and nothing in the
    output could tell that from a genuinely terrible squad.
    """
    assert real_points.missing_reports([1, 2, 3], {1: 4, 2: 0}) == [3]


def test_a_real_zero_is_not_reported_missing():
    """Scoring nothing is an answer; having no report is not."""
    assert real_points.missing_reports([1, 2], {1: 0, 2: -3}) == []
