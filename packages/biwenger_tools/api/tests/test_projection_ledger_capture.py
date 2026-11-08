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
        patch.object(cap, "reports_for_rounds", lambda reports, ids: reports),
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


def _capture(ctx, league, rows=lambda *a, **k: [], outlook=lambda: [], scales=None):
    written = []
    with (
        patch.object(cap.oraculo, "fetch_team_outlook", outlook),
        patch.object(cap, "_oraculo_scales", scales or (lambda: {})),
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


def _outlook(matchday, team="Real Madrid"):
    return {"team": team, "matchday": matchday, "win": 0.7, "clean_sheet": 0.46}


def test_the_snapshot_carries_each_teams_outlook_for_its_round():
    """Win and clean-sheet chances from the morning of the projection, kept for
    the round it lands on, so a captain chosen on them can be graded later."""
    ctx = _capture_ctx()
    ctx.biwenger.get_round.return_value = {"id": 4910, "name": "Jornada 13"}
    rows = [_outlook(13), _outlook(14), _outlook(13, "Celta de Vigo")]

    _, written = _capture(ctx, lambda ctx: {}, outlook=lambda: rows)

    assert written[0]["team_outlook"] == [rows[0], rows[2]]


def test_a_failed_outlook_read_still_writes_our_own_projection():
    ctx = _capture_ctx()
    ctx.biwenger.get_round.return_value = {"id": 4910, "name": "Jornada 13"}

    def broken():
        raise RuntimeError("page changed")

    result, written = _capture(ctx, lambda ctx: {}, outlook=broken)

    assert result["written"] is True
    assert "team_outlook" not in written[0]


def test_the_snapshot_carries_both_oraculo_scales():
    scales = {"fortuno-1": {"page": 4.91, "api": 8.21, "chance": 80}}

    _, written = _capture(_capture_ctx(), lambda ctx: {}, scales=lambda: scales)

    assert written[0]["oraculo_scales"] == scales


def test_a_failed_oraculo_scales_read_still_writes_our_own_projection():
    def broken():
        raise RuntimeError("page changed")

    result, written = _capture(_capture_ctx(), lambda ctx: {}, scales=broken)

    assert result["written"] is True
    assert "oraculo_scales" not in written[0]


def _collect(document, outcome, missing):
    ctx = MagicMock()
    ctx.biwenger.get_round.return_value = {
        "season": {"rounds": [{"id": 5176, "status": "finished"}]}
    }
    written = []
    with (
        patch.object(cap.projection_ledger_store, "list_all", lambda: [document]),
        patch.object(
            cap, "_outcome_for", lambda ctx, rid, ids, **k: (outcome, missing)
        ),
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


def test_a_player_whose_game_was_postponed_is_scored_from_the_sibling_round():
    """His report is filed under the postponed round's id. Read from the
    matchday, not from one id, he scores what he scored, never zero."""
    ctx = _ctx({})
    ctx.biwenger_players = {1: {"slug": "p1"}}
    ctx.biwenger.get_player_reports.side_effect = lambda slug: {
        "position": 2,
        "reports": [
            {
                "match": {"round": {"id": 5176}},
                "rawStats": {"minutesPlayed": 72, "score2": 6},
            }
        ],
    }
    with patch.object(cap.time, "sleep", lambda s: None):
        outcome, missing = cap._outcome_for(ctx, 5125, [], matchday=[5125, 5176])

    assert missing == []
    assert outcome["player_points"][1] > 0


def _collect_matchday(documents, season_rounds):
    ctx = MagicMock()
    ctx.biwenger.get_round.return_value = {"season": {"rounds": season_rounds}}
    written, outcome_calls = [], []
    with (
        patch.object(cap.projection_ledger_store, "list_all", lambda: documents),
        patch.object(
            cap,
            "_outcome_for",
            lambda *a, **k: outcome_calls.append((a, k)) or ({"applied_total": 1}, []),
        ),
        patch.object(
            cap.projection_ledger_store,
            "write_actual",
            lambda season, rid, actual: written.append((rid, actual)),
        ),
    ):
        result = cap.collect(ctx)
    return result, written, outcome_calls


def test_a_sibling_of_a_collected_matchday_is_covered_without_a_read():
    """5176's eleven was captured on 21/10 but never applied — Biwenger kept
    J6's September lineup. Its matchday already has an outcome under 5125,
    so it is marked as covered by it, costs no read and is never graded."""
    rounds = [
        {"id": 5125, "name": "Jornada 6 (aplazada)", "status": "finished"},
        {"id": 5176, "name": "Jornada 6 (aplazada)", "status": "finished"},
    ]
    docs = [
        {"round_id": 5125, "season": "26-27", "actual": {"applied_total": 46}},
        {"round_id": 5176, "season": "26-27", "captured_at": "2026-10-21T09:00"},
    ]
    result, written, outcome_calls = _collect_matchday(docs, rounds)

    assert result["covered"] == 5176
    assert outcome_calls == []
    assert written[0][0] == 5176
    assert written[0][1]["covered_by"] == 5125
    assert "player_points" not in written[0][1]


def test_a_matchday_with_a_game_still_to_play_is_not_collected():
    rounds = [
        {"id": 4920, "name": "Jornada 22", "status": "finished"},
        {"id": 5300, "name": "Jornada 22 (aplazada)", "status": "pending"},
    ]
    docs = [{"round_id": 4920, "season": "26-27", "captured_at": "2026-01-01T09:00"}]
    result, written, outcome_calls = _collect_matchday(docs, rounds)

    assert result == {"skipped": "nothing_pending"}
    assert written == [] and outcome_calls == []


def test_a_collected_matchday_reads_every_part_of_it():
    rounds = [
        {"id": 4920, "name": "Jornada 22", "status": "finished"},
        {"id": 5300, "name": "Jornada 22 (aplazada)", "status": "finished"},
    ]
    docs = [{"round_id": 4920, "season": "26-27", "captured_at": "2026-01-01T09:00"}]
    result, written, outcome_calls = _collect_matchday(docs, rounds)

    assert result["collected"] == 4920
    args, kwargs = outcome_calls[0]
    assert args[1] == 4920
    assert kwargs["matchday"] == [4920, 5300]
