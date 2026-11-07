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
        outcome, missing = cap._outcome_for(ctx, 4910, squad_ids=[1, 2])

    assert missing == []

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


def _capture(ctx, league, rows=lambda *a, **k: []):
    written = []
    with (
        patch.object(cap.projection_ledger, "target_round", lambda data, now: 4910),
        patch.object(cap, "build_squad_rows", rows),
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


def _jp_row(bw_id, rate):
    return {"bw_id": bw_id, "jp_player": {"predict": [{"type": 2, "rate": rate}]}}


def test_the_snapshot_carries_jornada_perfectas_number_for_every_player():
    """Whether a fixture moves the projection can only be measured on the
    whole competition: our own squad meets Barcelona a few times a season."""
    ctx = _capture_ctx()
    ctx.biwenger_players = {7: {"id": 7}, 9: {"id": 9}}

    def rows(squad, *a, **k):
        return [_jp_row(p["id"], 400 + p["id"]) for p in squad]

    _, written = _capture(ctx, lambda ctx: {}, rows)
    assert written[0]["league_jp"] == {"7": 407, "9": 409}


def test_a_failed_league_jp_read_still_writes_our_own_projection():
    ctx = _capture_ctx()
    ctx.biwenger_players = {7: {"id": 7}}

    def rows(squad, *a, **k):
        if squad:
            raise RuntimeError("matching blew up")
        return []

    result, written = _capture(ctx, lambda ctx: {}, rows)
    assert result["written"] is True
    assert "league_jp" not in written[0]


def _collect(document, outcome, missing):
    ctx = MagicMock()
    ctx.biwenger.get_round.return_value = {
        "season": {"rounds": [{"id": 5176, "status": "finished"}]}
    }
    written = []
    with (
        patch.object(cap.projection_ledger_store, "list_all", lambda: [document]),
        patch.object(cap, "_outcome_for", lambda ctx, rid, ids: (outcome, missing)),
        patch.object(
            cap.projection_ledger_store,
            "write_actual",
            lambda season, rid, actual: written.append((rid, actual)),
        ),
    ):
        result = cap.collect(ctx)
    return result, written


def test_a_round_refused_for_a_week_is_marked_and_never_read_again():
    """The refusal is right — no report must not become a zero — but retried
    forever it spends the player budget every morning for nothing."""
    document = {"round_id": 5176, "season": "26-27", "captured_at": "2026-10-21T09:00"}
    result, written = _collect(document, None, [2600, 947])

    assert result["refused"] == 5176
    assert written[0][0] == 5176
    assert written[0][1]["refused"] == "missing_reports"
    assert written[0][1]["missing"] == [947, 2600]
    assert "player_points" not in written[0][1]


def test_a_fresh_refusal_writes_nothing_and_is_retried_tomorrow():
    document = {"round_id": 5176, "season": "26-27", "captured_at": "2099-01-01T09:00"}
    result, written = _collect(document, None, [947])

    assert result == {"skipped": "incomplete", "round_id": 5176}
    assert written == []
