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
                    "name": "Me",
                    "points": 10,
                    "lineup": {
                        "type": "4-4-2",
                        "points": 10,
                        "players": [1],
                        "captain": {"id": 1},
                    },
                },
                {"id": 8, "name": "Rival", "points": 40, "lineup": {"points": 30}},
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
    assert outcome["league_points"] == [
        {"id": 7, "name": "Me", "points": 10},
        {"id": 8, "name": "Rival", "points": 30},
    ]


def _capture_ctx():
    ctx = MagicMock()
    ctx.biwenger.get_round.return_value = {"id": 4910}
    ctx.biwenger.get_manager_squad.return_value = []
    return ctx


def _capture(ctx, league):
    written = []
    with (
        patch.object(cap.projection_ledger, "target_round", lambda data, now: 4910),
        patch.object(cap, "build_squad_rows", lambda *a, **k: []),
        patch.object(
            cap.projection_ledger,
            "build_snapshot",
            lambda rid, name, season, rows, now: {"round_id": rid, "xi_differs": False},
        ),
        patch.object(cap.projection_ledger_store, "write", written.append),
        patch.object(cap.league_compare, "collect_cached", league),
    ):
        result = cap.capture(ctx)
    return result, written


def test_the_snapshot_carries_every_squads_projected_eleven():
    """Ranking the league by projection and by result needs every squad's
    projection from the same morning as ours."""

    def league(ctx):
        return {"Me": {"eleven": 5088}, "Rival": {"eleven": 4700}}

    result, written = _capture(_capture_ctx(), league)
    assert result["written"] is True
    assert written[0]["league_projection"] == {"Me": 5088, "Rival": 4700}


def test_a_failed_league_read_still_writes_our_own_projection():
    """The league is the extra; our own projection is the record. A rate limit
    on eight squad reads must not cost it."""

    def broken(ctx):
        raise RuntimeError("429")

    result, written = _capture(_capture_ctx(), broken)
    assert result["written"] is True
    assert "league_projection" not in written[0]
