"""Tests for measuring what the daily market actually takes to win.

Board entries follow `league/{id}/board`'s `market` shape: `to` the winner,
`amount` the winning bid, `bids[]` up to three losing ones.
Spec: `openspec/specs/biwenger_tools/auto-bid/spec.md`.
"""

from packages.biwenger_tools.api.logic import auction_calibration as ac

ME, RAYO, KAIRAT = 1, 2, 3
START = 1_784_015_094


def _u(uid, name=None):
    return {"id": uid, "name": name or f"user{uid}"}


def _market(player, winner, amount, date, bids=()):
    return {
        "type": "market",
        "date": date,
        "content": [
            {
                "player": player,
                "to": _u(winner),
                "amount": amount,
                "bids": [{"user": _u(u), "amount": a} for u, a in bids],
            }
        ],
    }


def _board(*entries):
    season = {"type": "seasonStarted", "content": {}, "date": START}
    return [season, *entries]


def test_auctions_come_off_the_board_with_winner_and_losing_bids():
    board = _board(
        _market(
            31027,
            RAYO,
            16_970_000,
            START + 10,
            [(ME, 16_375_999), (KAIRAT, 15_300_000)],
        )
    )
    (a,) = ac.auctions(board, my_id=ME)
    assert (a.player_id, a.winner_id, a.winning_bid) == (31027, RAYO, 16_970_000)
    assert a.runner_up == 16_375_999
    assert a.my_bid == 16_375_999 and not a.won_by_me


def test_last_seasons_auctions_are_left_out():
    board = _board(_market(1, RAYO, 1_000_000, START - 5))
    assert ac.auctions(board, my_id=ME) == []


def test_price_on_reads_the_day_before_the_auction_closed():
    """The auction closes in the morning; the asking price was the day before."""
    history = {260921: 7_760_000, 260922: 7_900_000}
    closed = 1_790_053_371  # 22/09/2026 07:02 Madrid
    assert ac.price_on(history, closed) == 7_760_000


def _priced(price, win, winner=RAYO, runner_up=None, mine=None):
    return ac.Auction(
        player_id=1,
        closed=START,
        winner_id=winner,
        winner_name=f"user{winner}",
        winning_bid=win,
        runner_up=runner_up,
        my_bid=mine,
        won_by_me=winner == ME,
        price=price,
    )


def test_win_rate_counts_the_bids_a_share_would_have_beaten():
    rows = [_priced(1_000_000, 1_020_000), _priced(1_000_000, 1_300_000)]
    assert ac.win_rate(rows, 0.05) == 0.5
    assert ac.win_rate(rows, 0.40) == 1.0


def test_share_to_win_finds_the_smallest_share_reaching_the_target():
    rows = [_priced(1_000_000, 1_000_000 + 10_000 * i) for i in range(10)]
    # overbids 0 %, 1 %, … 9 %: beating 8 of 10 needs more than 7 %
    assert ac.share_to_win(rows, 0.8) == 0.08


def test_left_on_the_table_is_what_we_paid_over_the_next_best():
    rows = [
        _priced(11_590_000, 14_850_126, winner=ME, runner_up=11_610_000),
        _priced(1_360_000, 2_040_776, winner=ME),  # nobody else: price is the floor
        _priced(5_000_000, 6_000_000),  # not ours
    ]
    assert ac.left_on_the_table(rows) == (14_850_126 - 11_610_000) + (
        2_040_776 - 1_360_000
    )


def test_overbid_by_winner_takes_the_median_per_manager():
    rows = [
        _priced(10_000_000, 11_000_000, winner=RAYO),
        _priced(10_000_000, 13_000_000, winner=RAYO),
        _priced(10_000_000, 12_000_000, winner=RAYO),
        _priced(10_000_000, 10_000_000, winner=KAIRAT),
    ]
    got = ac.overbid_by_winner(rows, min_price=5_000_000)
    assert got["user2"] == (3, 0.2)
    assert got["user3"] == (1, 0.0)
