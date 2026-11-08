"""Tests for `logic/squad_gap.py`.

The question is where a manager's league points come from: the SofaScore base
the projections rank by, or the league's own bonuses for playing, winning and
keeping a clean sheet — and whether a round is won by the whole eleven or by
its top two.
"""

from packages.biwenger_tools.api.logic import squad_gap as sg
from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID


def _stats(points, base=None, long_games=1, wins=0, losses=0, clean=0, games=1):
    return {
        "points": points,
        "sofascore_real": points if base is None else base,
        "games": games,
        "long_games": long_games,
        "wins": wins,
        "losses": losses,
        "clean_sheets": clean,
    }


DID_NOT_PLAY = _stats(0, long_games=0, games=0)


# ---------------------------------------------------------------------------
# counted
# ---------------------------------------------------------------------------


def test_a_starter_who_did_not_play_is_replaced_by_the_reserve_of_his_line():
    """Biwenger's bench has one reserve per line, in the order keeper,
    defender, midfielder, forward."""
    lineup = {"players": [1, 2, 3], "reserves": [10, 20, 30, 40]}
    positions = {1: GK, 2: DEF, 3: MID, 10: GK, 20: DEF, 30: MID, 40: FWD}
    played = {1, 3, 20, 30}

    assert sg.counted(lineup, played, positions) == [1, 20, 3]


def test_a_reserve_who_did_not_play_replaces_nobody():
    lineup = {"players": [1, 2], "reserves": [None, 20, None, None]}
    positions = {1: GK, 2: DEF, 20: DEF}

    assert sg.counted(lineup, {1}, positions) == [1]


def test_an_empty_slot_in_the_eleven_counts_nobody():
    lineup = {"players": [1, None], "reserves": [None, 20, None, None]}
    positions = {1: GK, 20: DEF}

    assert sg.counted(lineup, {1, 20}, positions) == [1]


# ---------------------------------------------------------------------------
# manager_round
# ---------------------------------------------------------------------------


def test_the_total_splits_into_base_play_result_clean_sheet_and_the_rest():
    lineup = {"players": [1, 2], "reserves": [], "captain": {"id": 2}}
    positions = {1: GK, 2: DEF}
    # Keeper: base 5, played, won, clean sheet (+2) → 9.
    # Defender: base 3, played, lost, a yellow (-1) → 2.
    stats = {
        1: _stats(9, base=5, wins=1, clean=1),
        2: _stats(2, base=3, losses=1),
    }

    row = sg.manager_round(lineup, stats, positions)

    # The captain counts twice, bonuses and all.
    assert row["points"] == 9 + 2 * 2
    assert row["base"] == 5 + 2 * 3
    assert row["play"] == 1 + 2 * 1
    assert row["result"] == 1 + 2 * -1
    assert row["clean"] == 2
    assert row["other"] == 2 * -1
    assert row["points"] == sum(
        row[k] for k in ("base", "play", "result", "clean", "other")
    )


def test_wins_and_losses_count_players_not_the_captain_twice():
    lineup = {"players": [1, 2], "reserves": [], "captain": {"id": 1}}
    stats = {1: _stats(5, wins=1), 2: _stats(1, losses=1)}

    row = sg.manager_round(lineup, stats, {1: MID, 2: FWD})

    assert (row["wins"], row["losses"]) == (1, 1)


def test_a_captain_who_did_not_play_doubles_nothing():
    lineup = {"players": [1, 2], "reserves": [], "captain": {"id": 2}}
    stats = {1: _stats(5), 2: DID_NOT_PLAY}

    assert sg.manager_round(lineup, stats, {1: MID, 2: FWD})["points"] == 5


def test_top_two_is_the_share_of_the_round_from_its_two_best_players():
    """The ceiling hypothesis: rounds are won by one or two explosive players
    rather than by the eleven."""
    lineup = {"players": [1, 2, 3], "reserves": [], "captain": {"id": 3}}
    stats = {1: _stats(10), 2: _stats(6), 3: _stats(2)}

    row = sg.manager_round(lineup, stats, {1: MID, 2: MID, 3: FWD})

    assert row["points"] == 10 + 6 + 2 * 2
    assert row["top_two"] == 16


# ---------------------------------------------------------------------------
# summarize
# ---------------------------------------------------------------------------


def test_summary_adds_each_managers_rounds_and_ranks_by_points_per_round():
    """Per round, because a manager with a round missing a report has fewer."""
    rows = {
        "A": [
            {
                "points": 50,
                "base": 40,
                "play": 8,
                "result": 2,
                "clean": 1,
                "other": -1,
                "wins": 4,
                "losses": 3,
                "top_two": 20,
            },
            {
                "points": 60,
                "base": 45,
                "play": 9,
                "result": 4,
                "clean": 2,
                "other": 0,
                "wins": 5,
                "losses": 1,
                "top_two": 30,
            },
        ],
        "B": [
            {
                "points": 70,
                "base": 50,
                "play": 10,
                "result": 6,
                "clean": 3,
                "other": 1,
                "wins": 7,
                "losses": 1,
                "top_two": 21,
            },
        ],
    }

    summary = sg.summarize(rows)

    assert [s["manager"] for s in summary] == ["B", "A"]
    a = summary[1]
    assert (a["rounds"], a["points"], a["base"], a["bonus"]) == (2, 110, 85, 25)
    assert (a["wins"], a["losses"]) == (9, 4)
    assert a["top_two_share"] == 50 / 110
