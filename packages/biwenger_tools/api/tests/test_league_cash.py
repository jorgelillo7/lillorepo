"""Tests for rebuilding every manager's cash from the league board.

Entry shapes are the ones `league/{id}/board` really returns — each type's
`content` copied from a live read, trimmed to the keys the rebuild reads.
Spec: `openspec/specs/biwenger_tools/league-cash/spec.md`.
"""

import pytest

from packages.biwenger_tools.api.logic import league_cash

START = 50_000_000
SEASON_START = 1_784_015_094
ME, RIVAL, OTHER = 1, 2, 3


def _user(uid):
    return {"id": uid, "name": f"user{uid}", "icon": ""}


def _entry(type_, content, date):
    return {"type": type_, "content": content, "date": date}


def _season_started(date=SEASON_START):
    return _entry("seasonStarted", {"season": {"id": "2027"}}, date)


def _round(round_id, payouts, date):
    results = [{"user": _user(uid), "bonus": bonus} for uid, bonus in payouts]
    return _entry(
        "roundFinished", {"round": {"id": round_id}, "results": results}, date
    )


def _rebuild(*entries):
    """Newest first, the order the board pages in."""
    ordered = sorted(entries, key=lambda e: e["date"], reverse=True)
    return league_cash.rebuild(ordered, START)


# --- Requirement: cash is the starting balance plus every movement ---------


def test_every_movement_kind_moves_the_right_side():
    t = SEASON_START
    book = _rebuild(
        _season_started(),
        _entry(
            "adminTransfer",
            [{"player": 10, "to": _user(ME), "amount": 3_000_000, "admin": _user(ME)}],
            t + 1,
        ),
        _entry("market", [{"player": 11, "to": _user(ME), "amount": 1_000_000}], t + 2),
        _entry(
            "transfer", [{"player": 12, "from": _user(ME), "amount": 400_000}], t + 3
        ),
        _entry(
            "transfer",
            [
                {
                    "player": 13,
                    "from": _user(RIVAL),
                    "to": _user(ME),
                    "amount": 5_000_000,
                    "type": "clause",
                }
            ],
            t + 4,
        ),
        _entry(
            "clauseIncrement",
            [{"user": _user(ME), "player": 13, "amount": 700_000, "releaseClause": 1}],
            t + 5,
        ),
        _entry("bonus", [{"user": _user(ME), "amount": 2_000_000}], t + 6),
        _round(4901, [(ME, 3_125_000), (RIVAL, 1_000_000)], t + 7),
    )
    assert (
        book.cash[ME]
        == (START - 3_000_000 - 1_000_000 + 400_000 - 5_000_000 - 700_000)
        + 2_000_000
        + 3_125_000
    )
    assert book.cash[RIVAL] == START + 5_000_000 + 1_000_000


def test_a_manager_with_no_entries_keeps_the_starting_balance():
    book = _rebuild(_season_started())
    assert book.cash_of(OTHER) == START


# --- Requirement: a clause refund adds cash --------------------------------


def test_a_negative_clause_increment_is_a_refund():
    t = SEASON_START
    book = _rebuild(
        _season_started(),
        _entry("clauseIncrement", [{"user": _user(ME), "amount": 2_000_000}], t + 1),
        _entry("clauseIncrement", [{"user": _user(ME), "amount": -1_500_000}], t + 2),
    )
    assert book.cash[ME] == START - 500_000


# --- Requirement: a score correction restates the round --------------------


def test_a_republished_round_counts_once_and_the_latest_wins():
    t = SEASON_START
    book = _rebuild(
        _season_started(),
        _round(4901, [(ME, 5_325_000)], t + 10),
        _round(4901, [(ME, 5_400_000)], t + 20),
    )
    assert book.cash[ME] == START + 5_400_000


# --- Requirement: only the current season counts ---------------------------


def test_entries_before_the_season_start_are_ignored():
    book = _rebuild(
        _entry("market", [{"to": _user(ME), "amount": 9_000_000}], SEASON_START - 5),
        _season_started(SEASON_START - 100_000),
        _season_started(),
    )
    assert book.cash_of(ME) == START


def test_a_read_that_never_reaches_the_season_start_raises():
    entries = [_entry("market", [{"to": _user(ME), "amount": 1}], SEASON_START)]
    with pytest.raises(ValueError, match="seasonStarted"):
        league_cash.rebuild(entries, START)


# --- Requirement: the maximum bid ------------------------------------------


def test_max_bid_is_cash_plus_a_quarter_of_the_squad():
    assert league_cash.max_bid(89_890, 67_210_000) == 16_892_390


def test_squad_value_sums_catalogue_prices():
    players = {10: {"price": 1_000_000}, 11: {"price": 2_500_000}}
    squad = [{"id": 10}, {"id": 11}, {"id": 99}]
    assert league_cash.squad_value(squad, players) == 3_500_000


# --- Requirement: the figures check themselves -----------------------------


def test_notes_confirm_a_matching_self_check():
    notes = league_cash.notes(
        frozenset(), rebuilt_mine=16_376_085, real_mine=16_376_085
    )
    assert any("cuadra" in n for n in notes)
    assert not any("⚠️" in n for n in notes)


def test_notes_give_both_figures_when_the_self_check_fails():
    notes = league_cash.notes(
        frozenset(), rebuilt_mine=21_701_085, real_mine=16_376_085
    )
    warning = next(n for n in notes if "⚠️" in n)
    assert "21.701.085" in warning and "16.376.085" in warning


def test_an_unknown_type_with_an_amount_is_reported():
    book = _rebuild(
        _season_started(),
        _entry(
            "loan",
            [{"from": _user(ME), "to": _user(RIVAL), "amount": 1}],
            SEASON_START + 1,
        ),
    )
    assert book.unknown_types == frozenset({"loan"})
    notes = league_cash.notes(book.unknown_types, rebuilt_mine=1, real_mine=1)
    assert any("loan" in n and "⚠️" in n for n in notes)


def test_an_unknown_type_without_an_amount_is_ignored():
    book = _rebuild(
        _season_started(),
        _entry("playerMovements", [{"type": "leave", "player": 1}], SEASON_START + 1),
        _entry("sticker", {"sticker": {"id": 1}}, SEASON_START + 2),
    )
    assert book.unknown_types == frozenset()


def test_a_moneyless_type_that_starts_carrying_an_amount_is_reported():
    """No `bettingPool` has ever carried money; the first prize must not be
    waved through because the type was on the known-harmless list."""
    book = _rebuild(
        _season_started(),
        _entry("bettingPool", {"winner": _user(ME), "amount": 1}, SEASON_START + 1),
    )
    assert book.unknown_types == frozenset({"bettingPool"})


def test_a_transfer_of_an_unseen_kind_is_reported():
    """Only plain and `clause` transfers have been seen. An exchange would most
    likely arrive as a transfer with a new `type`, and must be named."""
    move = {"from": _user(ME), "to": _user(RIVAL), "amount": 1, "type": "exchange"}
    book = _rebuild(_season_started(), _entry("transfer", [move], SEASON_START + 1))
    assert book.unknown_types == frozenset({"transfer:exchange"})


# --- Requirement: `/saldos` ranks richest first ----------------------------


def test_rows_are_ranked_by_max_bid():
    rows = league_cash.ranked(
        [
            {"name": "a", "cash": 30, "max_bid": 40},
            {"name": "b", "cash": 1, "max_bid": 90},
            {"name": "c", "cash": 50, "max_bid": 60},
        ]
    )
    assert [r["name"] for r in rows] == ["b", "c", "a"]


# --- Requirement: who can pay a clause of mine -----------------------------

RIVALS = [
    {"name": "Luceneta", "cash": 35_954_400, "max_bid": 52_386_900, "pacted": False},
    {"name": "Kairat", "cash": 3_833_440, "max_bid": 20_725_940, "pacted": True},
    {"name": "Reich", "cash": 89_890, "max_bid": 16_892_390, "pacted": False},
]
NOW = 1_790_000_000
DAY = 86_400


def test_reach_splits_rivals_by_cash_and_by_max_bid():
    got = league_cash.reach(12_500_025, RIVALS)
    assert [r["name"] for r in got.by_cash] == ["Luceneta"]
    assert [r["name"] for r in got.by_max_bid] == ["Kairat", "Reich"]


def test_reach_is_nobody_above_every_max_bid():
    got = league_cash.reach(60_000_000, RIVALS)
    assert not got.by_cash and not got.by_max_bid and not got.anyone


def _mine(name, score, clause, locked_until=None):
    return {
        "name": name,
        "position_id": 3,
        "custom_prediction": score,
        "clause_value": clause,
        "clause_locked_until": locked_until,
    }


def test_protection_ending_keeps_only_locks_ending_inside_the_window():
    rows = [
        _mine("already open", 500, 1, NOW - 60),
        _mine("ends tonight", 500, 1, NOW + DAY // 2),
        _mine("ends next week", 500, 1, NOW + 7 * DAY),
        _mine("never locked", 500, 1, None),
    ]
    ending = league_cash.protection_ending(rows, now=NOW, within=DAY)
    assert [r["name"] for r in ending] == ["ends tonight"]


def test_exposed_takes_the_best_projections_first():
    rows = [
        _mine("c", 300, 1),
        _mine("a", 700, 1),
        _mine("none", None, 1),
        _mine("b", 500, 1),
        _mine("d", 100, 1),
    ]
    assert [r["name"] for r in league_cash.exposed(rows, 3)] == ["a", "b", "c"]


def test_protection_alert_names_who_can_pay_and_marks_the_pact():
    row = _mine("Parrott", 400, 10_878_292, NOW + DAY // 2)
    text = league_cash.protection_alert([row], RIVALS)
    assert "Parrott" in text and "10.878.292" in text
    assert "Luceneta" in text
    assert "Kairat (pacto)" in text
    assert text.index("Luceneta") < text.index("Kairat")


def test_protection_alert_is_silent_when_nobody_reaches():
    row = _mine("Caro", 400, 90_000_000, NOW + DAY // 2)
    assert league_cash.protection_alert([row], RIVALS) is None


def test_exposure_rows_count_who_reaches_each_top_player():
    rows = [_mine("Gueye", 600, 12_500_025), _mine("Parrott", 400, 60_000_000)]
    got = league_cash.exposure_rows(rows, RIVALS)
    assert got[0] == {
        "name": "Gueye",
        "projection": 600,
        "clause": 12_500_025,
        "by_cash": 1,
        "by_max_bid": 2,
        "locked_until": None,
    }
    assert got[1]["by_cash"] == 0 and got[1]["by_max_bid"] == 0
