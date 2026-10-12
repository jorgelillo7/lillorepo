"""Tests for `trader`: which players to sell and buy on price streaks, inside
the owner's two limits — an available eleven, and no risk on a round's eve."""

from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID
from packages.biwenger_tools.api.logic.trader import (
    Rules,
    has_eleven,
    plan,
    report,
    round_eve,
)

RULES = Rules(
    sell_after_falls=2,
    buy_after_rises=3,
    buy_margin=0.03,
    buy_min_sf=300,
    max_squad=25,
)


def _player(bw_id, sf, position, price=2_000_000, called=True):
    return {
        "bw_id": bw_id,
        "name": f"P{bw_id}",
        "price": price,
        "position_id": position,
        "alt_positions": [],
        "jp_player": {
            "status": "ok",
            "nextMatch": {"status": "pending", "playerInLineup": called},
            "predict": [{"type": 2, "rate": sf}],
        },
    }


def _eleven():
    """Fills 4-4-2 exactly: selling any one of them leaves a hole."""
    return (
        [_player(1, 400, GK)]
        + [_player(10 + i, 400, DEF) for i in range(4)]
        + [_player(20 + i, 400, MID) for i in range(4)]
        + [_player(30 + i, 400, FWD) for i in range(2)]
    )


def _history(**moves):
    """Three days of prices; `moves` maps a player id to its daily change."""
    days = []
    for day in range(4):
        prices = {i: 2_000_000 for i in range(1, 100)}
        for pid, change in moves.items():
            prices[int(pid[1:])] = 2_000_000 + change * day
        days.append(prices)
    return days


def _plan(squad, market, history, cash=0, round_eve=False, limit=3_000_000):
    return plan(
        squad,
        market,
        history,
        cash=cash,
        round_eve=round_eve,
        negative_limit=limit,
        rules=RULES,
    )


# --- selling -----------------------------------------------------------------


def test_a_player_falling_two_days_is_sold_when_the_rest_still_fields_an_eleven():
    squad = _eleven() + [_player(40, 300, DEF)]
    result = _plan(squad, [], _history(p40=-50_000))
    assert [m.row["bw_id"] for m in result.sells] == [40]
    assert result.sells[0].amount == 2_000_000


def test_a_starter_of_the_best_eleven_is_never_sold_however_he_falls():
    """A good player is kept for his points; only the bench rotates on price."""
    star = _player(20, 900, MID)
    squad = [star] + [p for p in _eleven() if p["bw_id"] != 20]
    squad += [_player(40, 100, MID), _player(41, 100, DEF)]
    result = _plan(squad, [], _history(p20=-50_000, p40=-50_000))
    assert [m.row["bw_id"] for m in result.sells] == [40]
    assert (20, "titular del mejor once") in [
        (r["bw_id"], why) for r, why in result.held
    ]


def test_with_no_eleven_that_plays_even_the_bench_is_kept():
    """A squad already short of a playing eleven sells nobody: the bench is
    what covers the gap."""
    squad = _eleven()[:-1] + [_player(31, 200, FWD, called=False)]
    squad += [_player(40, 100, GK)]  # a second keeper never starts
    result = _plan(squad, [], _history(p40=-50_000))
    assert result.sells == []
    assert (40, "sin él no queda un once que juegue") in [
        (r["bw_id"], why) for r, why in result.held
    ]


def test_one_day_down_is_not_a_reason_to_sell():
    squad = _eleven() + [_player(40, 300, DEF)]
    history = [
        {40: 2_000_000},
        {40: 2_000_000},
        {40: 1_900_000},
    ]
    assert _plan(squad, [], history).sells == []


def test_a_player_the_projection_leaves_out_does_not_count_towards_the_eleven():
    """The eleven must be one that plays, not eleven names."""
    squad = _eleven()[:-1] + [_player(31, 200, FWD, called=False)]
    assert not has_eleven(squad)
    assert has_eleven(_eleven())


# --- buying ------------------------------------------------------------------


def test_a_market_player_rising_three_days_is_bid_just_over_his_price():
    market = [_player(50, 500, MID, price=3_000_000)]
    result = _plan(_eleven(), market, _history(p50=100_000), cash=5_000_000)
    assert [m.row["bw_id"] for m in result.buys] == [50]
    assert result.buys[0].amount == 3_090_000


def test_a_riser_below_the_projection_floor_is_not_bought():
    market = [_player(50, 200, MID, price=3_000_000)]
    result = _plan(_eleven(), market, _history(p50=100_000), cash=5_000_000)
    assert result.buys == []


def test_two_days_up_is_not_yet_a_trend():
    market = [_player(50, 500, MID, price=3_000_000)]
    history = [{50: 2_800_000}, {50: 2_800_000}, {50: 2_900_000}, {50: 3_000_000}]
    assert _plan(_eleven(), market, history, cash=5_000_000).buys == []


def test_the_best_projected_riser_is_bought_first():
    market = [
        _player(50, 350, MID, price=1_000_000),
        _player(51, 600, MID, price=1_000_000),
    ]
    result = _plan(
        _eleven(), market, _history(p50=10_000, p51=10_000), cash=1_100_000, limit=0
    )
    assert [m.row["bw_id"] for m in result.buys] == [51]


# --- the cash floor ----------------------------------------------------------


def test_away_from_a_round_the_wallet_may_go_negative_down_to_the_limit():
    market = [_player(50, 500, MID, price=3_000_000)]
    result = _plan(_eleven(), market, _history(p50=100_000), cash=0, limit=3_500_000)
    assert [m.row["bw_id"] for m in result.buys] == [50]
    assert result.cash_after == -3_090_000


def test_past_the_negative_limit_the_bid_is_skipped():
    market = [_player(50, 500, MID, price=3_000_000)]
    result = _plan(_eleven(), market, _history(p50=100_000), cash=0, limit=3_000_000)
    assert result.buys == []
    assert [(r["bw_id"], why) for r, why in result.skipped] == [
        (50, "no cabe en el saldo")
    ]


def test_on_a_round_s_eve_nothing_may_take_the_wallet_below_zero():
    market = [_player(50, 500, MID, price=3_000_000)]
    result = _plan(
        _eleven(),
        market,
        _history(p50=100_000),
        cash=1_000_000,
        round_eve=True,
        limit=10_000_000,
    )
    assert result.buys == []
    assert result.floor == 0


def test_today_s_sales_pay_for_today_s_buys():
    squad = _eleven() + [_player(40, 300, DEF, price=3_000_000)]
    market = [_player(50, 500, MID, price=2_500_000)]
    result = _plan(
        squad,
        market,
        _history(p40=-50_000, p50=100_000),
        cash=0,
        round_eve=True,
    )
    assert [m.row["bw_id"] for m in result.sells] == [40]
    assert [m.row["bw_id"] for m in result.buys] == [50]
    assert result.cash_after >= 0


def test_a_full_squad_buys_nobody():
    squad = _eleven() + [_player(60 + i, 100, DEF) for i in range(14)]
    market = [_player(50, 500, MID)]
    result = _plan(squad, market, _history(p50=100_000), cash=10_000_000)
    assert result.buys == []
    assert [why for _, why in result.skipped] == ["plantilla llena"]


# --- the report --------------------------------------------------------------


def test_the_report_says_it_is_a_simulation_and_names_every_move():
    squad = _eleven() + [_player(40, 300, DEF)]
    market = [_player(50, 500, MID, price=3_000_000)]
    result = _plan(squad, market, _history(p40=-50_000, p50=100_000), cash=5_000_000)
    text = report(result, live=False)
    assert "simulación" in text
    assert "P40" in text and "P50" in text


# --- the round's eve ---------------------------------------------------------

_NOW = 1_791_792_000  # Monday 12/10/2026 10:00 Madrid


def _round(status, *kickoffs):
    return {
        "status": status,
        "games": [{"date": k, "status": "pending"} for k in kickoffs],
    }


def test_a_round_starting_tomorrow_makes_today_its_eve():
    tomorrow_evening = _NOW + 36 * 3600
    assert round_eve([_round("pending", tomorrow_evening)], _NOW)


def test_a_round_three_days_out_is_not_its_eve():
    assert not round_eve([_round("pending", _NOW + 3 * 86400)], _NOW)


def test_the_rest_of_a_round_already_under_way_does_not_count_as_a_start():
    rounds = [
        _round("active", _NOW + 10 * 3600),
        _round("pending", _NOW + 4 * 86400),
    ]
    assert not round_eve(rounds, _NOW)


def test_an_unreadable_calendar_is_treated_as_an_eve():
    """Not knowing when the round starts is the one case to be careful in."""
    assert round_eve(None, _NOW)
    assert round_eve([], _NOW)
