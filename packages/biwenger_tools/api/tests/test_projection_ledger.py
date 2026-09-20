"""Tests for `logic/projection_ledger.py`.

The whole point of the ledger is the pair of elevens: the mornings the blend
and Jornada Perfecta alone agree teach nothing, the ones where they diverge
are the entire dataset `ORACULO_W` needs before it can be justified with
data instead of a guess. Every assertion below is built around that split.
"""

from datetime import datetime

from core.constants import MADRID_TZ
from packages.biwenger_tools.api.logic import projection_ledger as pl
from packages.biwenger_tools.api.logic.projection_ledger import (
    MIN_ROUNDS_FOR_VERDICT,
)
from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID
from packages.biwenger_tools.api.player_formatting import SCORE_SF

NOW = datetime(2026, 9, 20, 9, 0, tzinfo=MADRID_TZ)


def _kickoff(day: int, hour: int) -> int:
    return int(datetime(2026, 9, day, hour, tzinfo=MADRID_TZ).timestamp())


def _games(*hours: int, day: int = 20) -> list:
    return [{"status": "preview", "date": _kickoff(day, h)} for h in hours]


# ---------------------------------------------------------------------------
# target_round
# ---------------------------------------------------------------------------


def test_target_round_is_the_current_one_before_its_kickoff():
    """Saturday-morning read, before the round's first match: the pick this
    morning makes lands on the round already showing."""
    round_data = {"id": 4901, "games": _games(21)}  # 21:00 today, NOW is 09:00

    assert pl.target_round(round_data, NOW) == 4901


def test_target_round_is_next_once_the_current_one_has_kicked_off():
    """Under *jornada única* the current round is usually already under way
    by 09:00 (`openspec/project.md`, row 61): the lineup this morning sets
    lands on `next`, not on the round `get_round()` calls current."""
    round_data = {
        "id": 4901,
        "games": [{"status": "finished", "date": _kickoff(17, 21)}],
        "next": {"id": 4904, "games": _games(21)},
    }

    assert pl.target_round(round_data, NOW) == 4904


def test_target_round_is_none_when_neither_kickoff_is_confirmed():
    """No games data for either round: writing would be a guess about
    whether the matchday has started, and the ledger must never write on a
    guess — a stale but true silence beats a snapshot that might overwrite
    a round already under way."""
    round_data = {"id": 4901, "games": [], "next": {"id": 4904, "games": []}}

    assert pl.target_round(round_data, NOW) is None


def test_target_round_is_none_once_both_are_in_the_past():
    round_data = {
        "id": 4901,
        "games": [{"status": "finished", "date": _kickoff(17, 21)}],
        "next": {
            "id": 4904,
            "games": [{"status": "finished", "date": _kickoff(19, 21)}],
        },
    }

    assert pl.target_round(round_data, NOW) is None


def test_target_round_survives_a_malformed_payload():
    assert pl.target_round(None, NOW) is None
    assert pl.target_round("not a dict", NOW) is None
    assert pl.target_round({}, NOW) is None


# ---------------------------------------------------------------------------
# build_snapshot
# ---------------------------------------------------------------------------


def _row(bw_id, jp_sf, custom, position=MID, matched=True):
    return {
        "bw_id": bw_id,
        "name": f"P{bw_id}",
        "position_id": position,
        "alt_positions": [],
        "price": 500_000,
        "jp_player": {
            "status": "ok",
            "nextMatch": {"status": "pending", "playerInLineup": True},
            "predict": [{"type": SCORE_SF, "rate": jp_sf}],
        },
        "oraculo_matched": matched,
        "oraculo_points": custom,
        "oraculo_chance": 90,
        "custom_prediction": custom,
    }


def _squad_where_the_blend_swaps_a_forward():
    """15 rows filling 4-4-2 with three forwards competing for two slots.
    Jornada Perfecta alone ranks them 30 > 31 > 32; the blend inverts the
    bottom two so the eleven it fields is not the one JP alone would pick."""
    return (
        [_row(1, 500, 500, GK)]
        + [_row(10 + i, 400 - i, 400 - i, DEF) for i in range(4)]
        + [_row(20 + i, 300 - i, 300 - i, MID) for i in range(4)]
        + [
            _row(30, 200, 200, FWD),
            _row(31, 190, 40, FWD),
            _row(32, 40, 210, FWD),
        ]
    )


def _squad_where_nothing_moves():
    """Same shape, `custom_prediction` identical to `jp_sf` everywhere — the
    blend had nothing to disagree with."""
    return (
        [_row(1, 500, 500, GK)]
        + [_row(10 + i, 400 - i, 400 - i, DEF) for i in range(4)]
        + [_row(20 + i, 300 - i, 300 - i, MID) for i in range(4)]
        + [_row(30, 200, 200, FWD), _row(31, 190, 190, FWD), _row(32, 40, 40, FWD)]
    )


def test_the_snapshot_reports_two_elevens_that_actually_differ():
    rows = _squad_where_the_blend_swaps_a_forward()

    snapshot = pl.build_snapshot(4901, "Jornada 6", "26-27", rows, NOW)

    blended_ids = set(snapshot["blended_xi"]["player_ids"])
    jp_ids = set(snapshot["jp_only_xi"]["player_ids"])
    assert blended_ids != jp_ids
    assert snapshot["xi_differs"] is True
    assert snapshot["xi_diff"]["only_blended"] and snapshot["xi_diff"]["only_jp"]
    assert set(snapshot["xi_diff"]["only_blended"]) == blended_ids - jp_ids
    assert set(snapshot["xi_diff"]["only_jp"]) == jp_ids - blended_ids


def test_the_snapshot_says_so_when_the_two_elevens_agree():
    rows = _squad_where_nothing_moves()

    snapshot = pl.build_snapshot(4901, "Jornada 6", "26-27", rows, NOW)

    assert snapshot["blended_xi"]["player_ids"] == snapshot["jp_only_xi"]["player_ids"]
    assert snapshot["xi_differs"] is False
    assert snapshot["xi_diff"] == {"only_blended": [], "only_jp": []}


def test_the_snapshot_carries_every_provider_number_per_player():
    rows = _squad_where_nothing_moves()

    snapshot = pl.build_snapshot(4901, "Jornada 6", "26-27", rows, NOW)

    by_id = {p["bw_id"]: p for p in snapshot["players"]}
    assert by_id[30] == {
        "bw_id": 30,
        "name": "P30",
        "position_id": FWD,
        "jp_sf": 200,
        "oraculo_points": 200,
        "oraculo_matched": True,
        "custom_prediction": 200,
    }
    assert snapshot["season"] == "26-27"
    assert snapshot["round_id"] == 4901
    assert snapshot["round_name"] == "Jornada 6"
    assert snapshot["has_projection"] is True


def test_the_snapshot_survives_a_squad_with_no_legal_eleven():
    """Not enough matched positions to field anybody — `best_eleven` returns
    `None` for both runs, and the snapshot must say that rather than raise."""
    rows = [_row(1, 500, 500, GK)]

    snapshot = pl.build_snapshot(4901, "Jornada 6", "26-27", rows, NOW)

    assert snapshot["blended_xi"] is None
    assert snapshot["jp_only_xi"] is None
    assert snapshot["xi_differs"] is False


# ---------------------------------------------------------------------------
# xi_real_points
# ---------------------------------------------------------------------------


def test_xi_real_points_sums_and_doubles_the_captain():
    total = pl.xi_real_points([1, 2, 3], captain_id=2, real_points={1: 5, 2: 3, 3: -1})

    assert total == 5 + 3 * 2 + (-1)


def test_xi_real_points_treats_a_player_with_no_data_as_zero():
    """No report reached us for that player that round — he did not play,
    not `-4`: that penalty is Biwenger's for a slot left empty, and every
    slot here is filled."""
    total = pl.xi_real_points([1, 2], captain_id=None, real_points={1: 5})

    assert total == 5


# ---------------------------------------------------------------------------
# extract_applied_lineup
# ---------------------------------------------------------------------------


def test_extract_applied_lineup_finds_the_manager_by_id():
    data = {
        "league": {
            "standings": [
                {
                    "id": 1372802,
                    "points": 46,
                    "lineup": {
                        "type": "4-4-2",
                        "captain": {"id": 30},
                        "players": [1, 10, 11, 12, 13, 20, 21, 22, 23, 30, 31],
                        "reserves": [None, None, None, None],
                    },
                },
                {"id": 9999, "points": 12, "lineup": {}},
            ]
        }
    }

    applied = pl.extract_applied_lineup(data, user_id=1372802)

    assert applied == {
        "formation": "4-4-2",
        "player_ids": [1, 10, 11, 12, 13, 20, 21, 22, 23, 30, 31],
        "captain_id": 30,
        "points": 46,
    }


def test_extract_applied_lineup_drops_null_bench_slots():
    data = {
        "league": {
            "standings": [
                {
                    "id": 1,
                    "points": 0,
                    "lineup": {
                        "type": "4-4-2",
                        "captain": {},
                        "players": [1, None, None],
                        "reserves": [],
                    },
                }
            ]
        }
    }

    applied = pl.extract_applied_lineup(data, user_id=1)

    assert applied["player_ids"] == [1]
    assert applied["captain_id"] is None


def test_extract_applied_lineup_is_none_for_an_unknown_manager():
    data = {"league": {"standings": [{"id": 1, "lineup": {}}]}}

    assert pl.extract_applied_lineup(data, user_id=2) is None


# --- grading: what the stored rounds add up to, and when to say nothing ----


def _graded(round_id, differs, blended, jp_only):
    return {
        "season": "26-27",
        "round_id": round_id,
        "has_projection": True,
        "xi_differs": differs,
        "blended_xi": {"player_ids": [1], "captain_id": None},
        "jp_only_xi": {"player_ids": [2], "captain_id": None},
        "actual": {"blended_total": blended, "jp_only_total": jp_only},
    }


def test_rounds_where_the_elevens_agreed_are_not_evidence():
    """A round both versions would have played identically says nothing about
    the blend. Counting it dilutes the signal towards zero with arithmetic
    rather than with evidence."""
    docs = [
        _graded(1, False, 50, 50),
        _graded(2, False, 61, 61),
        _graded(3, True, 48, 40),
    ]
    summary = pl.grade(docs)
    assert summary["rounds_stored"] == 3
    assert summary["rounds_compared"] == 1
    assert summary["deltas"] == [8]


def test_a_round_with_no_outcome_yet_is_not_counted():
    pending = _graded(4, True, 0, 0)
    del pending["actual"]
    summary = pl.grade([pending])
    assert summary["rounds_compared"] == 0


def test_a_backfilled_round_never_counts():
    """Seeded for the read path, with no projection to compare against."""
    doc = _graded(5, True, 50, 40)
    doc["has_projection"] = False
    assert pl.grade([doc])["rounds_compared"] == 0


def test_too_few_disagreements_refuses_a_verdict():
    """A script that prints a conclusion from three rounds invites a decision
    the data cannot support. The honest output is that it is too early."""
    docs = [_graded(i, True, 50, 40) for i in range(MIN_ROUNDS_FOR_VERDICT - 1)]
    summary = pl.grade(docs)
    assert summary["verdict"] is None
    assert summary["rounds_needed"] == 1


def test_a_verdict_appears_once_there_is_enough_to_read():
    docs = [_graded(i, True, 50, 40) for i in range(MIN_ROUNDS_FOR_VERDICT)]
    summary = pl.grade(docs)
    assert summary["verdict"] is not None
    assert summary["blend_won"] == MIN_ROUNDS_FOR_VERDICT
    assert summary["rounds_needed"] == 0


# --- which finished round still needs its outcome --------------------------


def test_the_oldest_round_without_an_outcome_is_next():
    """One per run, oldest first: a backlog drains a round a day instead of
    spending a morning's budget in one spike."""
    docs = [
        {"round_id": 7, "actual": {"applied_total": 3}},
        {"round_id": 9},
        {"round_id": 8},
    ]
    assert pl.next_round_to_collect(docs, {7, 8, 9}) == 8


def test_a_round_biwenger_has_not_finished_is_not_collected():
    """Under *jornada única* a round is not final until every match in it is
    played, so reading it early would store a partial total as if it were the
    result."""
    docs = [{"round_id": 8}]
    assert pl.next_round_to_collect(docs, set()) is None


def test_nothing_to_collect_is_not_an_error():
    assert pl.next_round_to_collect([], {1, 2}) is None
    assert pl.next_round_to_collect([{"round_id": 1, "actual": {}}], {1}) is None
