"""Tests for `projection_ledger_capture._outcome_for`: what a finished round
stores."""

from unittest.mock import MagicMock, patch

from packages.biwenger_tools.api.logic import projection_ledger_capture as cap


def _ctx(squad_points):
    ctx = MagicMock()
    ctx.biwenger.user_id = 7
    ctx.biwenger.get_round_league.return_value = {
        "league": {
            "standings": [
                {
                    "id": 7,
                    "points": 10,
                    "lineup": {"type": "4-4-2", "players": [1], "captain": {"id": 1}},
                }
            ]
        }
    }
    ctx.biwenger_players = {pid: {"slug": f"p{pid}"} for pid in squad_points}
    ctx.biwenger.get_player_reports.side_effect = lambda slug: {
        "reports": [{"pts": squad_points[int(slug[1:])]}],
        "position": 2,
    }
    return ctx


def test_a_finished_round_scores_the_whole_squad_not_only_the_eleven():
    """Yuri's 21 from the bench went unrecorded: the ledger only scored the
    eleven fielded, so it could never learn from who was left out."""
    ctx = _ctx({1: 5, 2: 21})
    with (
        patch.object(cap, "reports_for_round", lambda reports, rid: reports),
        patch.object(
            cap, "personalizado", lambda m, pos: {"points": m[0]["pts"] if m else 0}
        ),
        patch.object(cap.time, "sleep", lambda s: None),
    ):
        outcome = cap._outcome_for(ctx, 4910, squad_ids=[1, 2])

    assert outcome["player_points"] == {1: 5, 2: 21}
    assert outcome["applied_total"] == 10  # the eleven's score, captain doubled
