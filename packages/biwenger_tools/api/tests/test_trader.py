"""Tests for `trader`: which players to sell and buy on price streaks, inside
the owner's two limits — an available eleven, and no risk on a round's eve."""

from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID
from packages.biwenger_tools.api.logic.trader import (
    Move,
    Rules,
    has_eleven,
    plan,
    report,
    round_eve,
    sale_offers,
)

RULES = Rules(
    sell_after_falls=2,
    buy_after_rises=3,
    buy_margin=0.03,
    buy_min_sf=300,
    max_squad=25,
    min_squad=11,
    dead_sf=0,
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


# --- what the live run spends: pending bids, and the offers it may take -------


def test_pending_bids_are_spent_already_and_never_bid_twice():
    """Biwenger does not deduct a waiting bid from the balance, and a retried
    run must not bid on a player it already has a bid on."""
    market = [_player(50, 500, MID, price=3_000_000), _player(51, 400, MID)]
    result = plan(
        _eleven(),
        market,
        _history(p50=100_000, p51=100_000),
        cash=5_000_000,
        round_eve=True,
        negative_limit=0,
        rules=RULES,
        committed=2_000_000,
        already_bid={50},
    )
    assert [m.row["bw_id"] for m in result.buys] == [51]
    assert result.cash_after == 5_000_000 - 2_000_000 - 2_060_000


def _offer(offer_id, player, amount, from_id=None):
    return {
        "id": offer_id,
        "amount": amount,
        "requestedPlayers": [player],
        "from": {"id": from_id} if from_id else None,
    }


def test_the_best_offer_at_or_near_the_price_is_taken_for_each_planned_sell():
    sells = [Move(_player(40, 300, DEF, price=2_000_000), 2_000_000, -2)]
    inbox = [
        _offer(1, 40, 1_960_000),
        _offer(2, 40, 2_050_000, from_id=99),
        _offer(3, 40, 1_500_000),
    ]
    taken = sale_offers(sells, inbox, min_share=0.95)
    assert [(m.row["bw_id"], o["id"]) for m, o in taken] == [(40, 2)]


def test_an_offer_below_the_floor_is_not_taken():
    sells = [Move(_player(40, 300, DEF, price=2_000_000), 2_000_000, -2)]
    assert sale_offers(sells, [_offer(1, 40, 1_800_000)], min_share=0.95) == []


def test_an_offer_for_a_player_not_being_sold_is_never_taken():
    """The whole squad is listed every day; only the plan's sells are sold."""
    sells = [Move(_player(40, 300, DEF, price=2_000_000), 2_000_000, -2)]
    inbox = [_offer(1, 20, 9_000_000), _offer(2, 40, 2_000_000)]
    taken = sale_offers(sells, inbox, min_share=0.95)
    assert [o["id"] for _, o in taken] == [2]


def test_an_offer_for_several_players_is_never_taken():
    """Accepting it would sell a player the plan keeps."""
    sells = [Move(_player(40, 300, DEF, price=2_000_000), 2_000_000, -2)]
    offer = _offer(1, 40, 5_000_000)
    offer["requestedPlayers"] = [40, 20]
    assert sale_offers(sells, [offer], min_share=0.95) == []


def test_a_postponed_round_s_played_games_do_not_make_every_day_its_eve():
    """'Jornada 6 (aplazada)' stays pending with nine games played in
    September and one left: only the one left can start anything."""
    postponed = {
        "status": "pending",
        "games": [
            {"date": _NOW - 30 * 86400, "status": "finished"},
            {"date": _NOW + 8 * 86400, "status": "pending"},
        ],
    }
    assert not round_eve([postponed, _round("pending", _NOW + 4 * 86400)], _NOW)
    assert round_eve([postponed], _NOW + 7 * 86400)


# --- a bench is kept, and the weakest go first --------------------------------


def test_sales_stop_at_the_minimum_squad_so_a_bench_is_left():
    """Eleven are not enough: an injury the day before leaves a hole."""
    squad = _eleven() + [_player(40, 300, DEF), _player(41, 200, MID)]
    rules = Rules(**{**RULES.__dict__, "min_squad": 12})
    result = plan(
        squad,
        [],
        _history(p40=-50_000, p41=-50_000),
        cash=0,
        round_eve=False,
        negative_limit=0,
        rules=rules,
    )
    assert len(result.sells) == 1
    assert (40, "plantilla mínima") in [(r["bw_id"], why) for r, why in result.held]


def test_among_the_fallers_the_weakest_projection_is_sold_first():
    squad = _eleven() + [_player(40, 300, DEF), _player(41, 50, MID)]
    rules = Rules(**{**RULES.__dict__, "min_squad": 12})
    history = [
        {
            **{i: 2_000_000 for i in range(1, 100)},
            40: 2_600_000 - d * 200_000,
            41: 2_000_000 - d * 10_000,
        }
        for d in range(4)
    ]
    result = plan(
        squad, [], history, cash=0, round_eve=False, negative_limit=0, rules=rules
    )
    assert [m.row["bw_id"] for m in result.sells] == [41]


# --- the bench that will not do much is sold, whatever its price --------------

DEADWOOD = Rules(**{**RULES.__dict__, "dead_sf": 300})


def _flat():
    return [{i: 2_000_000 for i in range(1, 100)} for _ in range(4)]


def test_a_bench_player_projected_low_is_sold_even_on_a_flat_price():
    squad = _eleven() + [_player(40, 120, DEF)]
    result = plan(
        squad, [], _flat(), cash=0, round_eve=False, negative_limit=0, rules=DEADWOOD
    )
    assert [m.row["bw_id"] for m in result.sells] == [40]
    assert "proyección baja" in report(result, live=False)


def test_a_bench_player_who_projects_well_is_kept_on_a_flat_price():
    squad = _eleven() + [_player(40, 350, DEF)]
    result = plan(
        squad, [], _flat(), cash=0, round_eve=False, negative_limit=0, rules=DEADWOOD
    )
    assert result.sells == []


def test_a_starter_is_never_deadwood_however_low_he_projects():
    """A thin squad starts a weak player; selling him opens a hole."""
    squad = _eleven()[:-1] + [_player(31, 150, FWD)]
    result = plan(
        squad, [], _flat(), cash=0, round_eve=False, negative_limit=0, rules=DEADWOOD
    )
    assert result.sells == []


def test_deadwood_still_stops_at_the_minimum_squad():
    squad = _eleven() + [_player(40, 120, DEF), _player(41, 80, MID)]
    rules = Rules(**{**DEADWOOD.__dict__, "min_squad": 12})
    result = plan(
        squad, [], _flat(), cash=0, round_eve=False, negative_limit=0, rules=rules
    )
    assert [m.row["bw_id"] for m in result.sells] == [41]


# --- the eve is the day before; buys fill the thinnest line, never a keeper ----


def test_the_day_a_round_starts_is_not_its_eve():
    """A bid placed that morning settles the next morning, after kickoff."""
    tonight = _NOW + 11 * 3600  # Monday 21:00
    assert not round_eve([_round("pending", tonight)], _NOW)


def test_buys_go_to_the_thinnest_line_first():
    squad = _eleven() + [_player(40, 300, DEF), _player(41, 300, DEF)]
    market = [_player(50, 600, DEF), _player(51, 400, FWD)]
    result = plan(
        squad,
        market,
        _history(p50=100_000, p51=100_000),
        cash=2_100_000,
        round_eve=True,
        negative_limit=0,
        rules=RULES,
    )
    assert [m.row["bw_id"] for m in result.buys] == [51]


def test_a_goalkeeper_is_never_bought():
    """A manager's only keeper cannot be claused; a second one can."""
    market = [_player(50, 800, GK)]
    result = plan(
        _eleven(),
        market,
        _history(p50=100_000),
        cash=9_000_000,
        round_eve=False,
        negative_limit=0,
        rules=RULES,
    )
    assert result.buys == []


# --- the hold after a signing ------------------------------------------------

NOW = 1_792_000_000.0
DAY = 86_400
HOLD = Rules(**{**RULES.__dict__, "hold_days": 14, "dead_sf": 300})


def _signed(player, days_ago):
    return {**player, "acq_date": int(NOW - days_ago * DAY)}


def test_a_player_signed_under_two_weeks_ago_is_not_sold_for_falling():
    """Auto-bid signs on projection; selling him days later on a falling
    price buys high and sells low."""
    squad = _eleven() + [_signed(_player(40, 350, DEF), days_ago=3)]
    result = plan(
        squad,
        [],
        _history(p40=-50_000),
        cash=0,
        round_eve=False,
        negative_limit=0,
        rules=HOLD,
        now=NOW,
    )
    assert result.sells == []
    ((row, why),) = [(r, w) for r, w in result.held if r["bw_id"] == 40]
    assert why.startswith("fichado hace 3 días")


def test_the_hold_ends_after_two_weeks():
    squad = _eleven() + [_signed(_player(40, 350, DEF), days_ago=14)]
    result = plan(
        squad,
        [],
        _history(p40=-50_000),
        cash=0,
        round_eve=False,
        negative_limit=0,
        rules=HOLD,
        now=NOW,
    )
    assert [m.row["bw_id"] for m in result.sells] == [40]


def test_a_fresh_signing_projected_under_the_floor_is_held_too():
    """Auto-bid signs at SF 300 and the blend moves a few points a day: selling
    a five-day signing for dipping under the same 300 is churn, not judgement.
    The hold covers the projection floor as well as the price."""
    squad = _eleven() + [_signed(_player(40, 290, DEF), days_ago=5)]
    result = plan(
        squad,
        [],
        _history(p40=-50_000),
        cash=0,
        round_eve=False,
        negative_limit=0,
        rules=HOLD,
        now=NOW,
    )
    assert result.sells == []
    ((_, why),) = [(r, w) for r, w in result.held if r["bw_id"] == 40]
    assert why.startswith("fichado hace 5 días")


def test_a_faller_also_under_the_floor_is_sold_naming_the_projection():
    """Past the hold, the report names the projection when it is below the
    floor, not only the falling price — that is what decides the sale."""
    squad = _eleven() + [_signed(_player(40, 290, DEF), days_ago=20)]
    result = plan(
        squad,
        [],
        _history(p40=-50_000),
        cash=0,
        round_eve=False,
        negative_limit=0,
        rules=HOLD,
        now=NOW,
    )
    (move,) = result.sells
    assert "proyección baja (SF 290)" in move.reason


def test_a_player_with_no_signing_date_is_not_held():
    squad = _eleven() + [{**_player(40, 350, DEF), "acq_date": None}]
    result = plan(
        squad,
        [],
        _history(p40=-50_000),
        cash=0,
        round_eve=False,
        negative_limit=0,
        rules=HOLD,
        now=NOW,
    )
    assert [m.row["bw_id"] for m in result.sells] == [40]


# --- no more than three players from one club --------------------------------

CLUB = Rules(**{**RULES.__dict__, "max_per_club": 3})


def _of(player, team_id):
    return {**player, "team_id": team_id}


def test_a_riser_from_a_club_already_three_deep_is_not_bought():
    squad = [_of(p, 7) if p["bw_id"] in (10, 11, 12) else p for p in _eleven()]
    market = [_of(_player(60, 400, MID), 7), _of(_player(61, 400, MID), 8)]
    result = plan(
        squad,
        market,
        _history(p60=50_000, p61=50_000),
        cash=10_000_000,
        round_eve=False,
        negative_limit=0,
        rules=CLUB,
    )
    assert [m.row["bw_id"] for m in result.buys] == [61]
    assert (60, "ya hay 3 de su equipo") in [
        (r["bw_id"], why) for r, why in result.skipped
    ]


def test_a_bid_already_waiting_counts_towards_the_club():
    squad = [_of(p, 7) if p["bw_id"] in (10, 11) else p for p in _eleven()]
    waiting = _of(_player(59, 400, DEF), 7)
    market = [waiting, _of(_player(60, 400, MID), 7)]
    result = plan(
        squad,
        market,
        _history(p60=50_000),
        cash=10_000_000,
        round_eve=False,
        negative_limit=0,
        rules=CLUB,
        already_bid={59},
    )
    assert result.buys == []


def test_bench_players_from_a_club_do_not_fill_its_cap():
    """Only the best eleven's starters count; three weak reserves from a club
    must not block a riser from it."""
    squad = _eleven() + [_of(_player(40 + i, 50, MID), 7) for i in range(3)]
    market = [_of(_player(60, 400, MID), 7)]
    result = plan(
        squad,
        market,
        _history(p60=50_000),
        cash=10_000_000,
        round_eve=False,
        negative_limit=0,
        rules=CLUB,
    )
    assert [m.row["bw_id"] for m in result.buys] == [60]


# --- squad shape: keepers, versatile players, bids already waiting -----------


def test_a_second_keeper_who_does_not_start_is_sold_on_a_flat_price():
    """A manager's only keeper cannot be claused; a second one exposes both,
    so the one left out of the eleven goes, whatever his price does."""
    squad = _eleven() + [_player(2, 350, GK), _player(40, 380, MID)]
    result = _plan(squad, [], _flat())
    assert [m.row["bw_id"] for m in result.sells] == [2]
    assert "portero" in result.sells[0].reason


def test_the_keeper_who_starts_is_never_the_one_sold():
    squad = _eleven() + [_player(2, 900, GK)]
    result = _plan(squad, [], _flat())
    assert [m.row["bw_id"] for m in result.sells] == [1]


def test_a_second_keeper_still_stops_at_the_minimum_squad():
    squad = _eleven() + [_player(2, 350, GK)]
    rules = Rules(**{**RULES.__dict__, "min_squad": 12})
    result = plan(
        squad, [], _flat(), cash=0, round_eve=False, negative_limit=0, rules=rules
    )
    assert result.sells == []
    assert [why for _, why in result.held] == ["plantilla mínima"]


def test_a_versatile_player_covers_every_line_he_can_play():
    """The thinnest line goes first, and a DEF/MID counts on both: with four
    midfielders, four forwards and a DEF/MID spare, forward is the thin line."""
    spare = dict(_player(40, 300, DEF), alt_positions=[MID])
    squad = _eleven() + [spare, _player(41, 300, FWD), _player(42, 300, FWD)]
    market = [_player(50, 500, MID), _player(51, 400, FWD)]
    result = _plan(squad, market, _history(p50=100_000, p51=100_000), cash=10_000_000)
    assert [m.row["bw_id"] for m in result.buys][0] == 51


def test_bids_already_waiting_count_towards_a_full_squad():
    """The morning's auto-bids land in the squad too; buying past them would
    take it over the maximum."""
    squad = _eleven() + [_player(60 + i, 100, DEF) for i in range(13)]
    market = [_player(50, 500, MID)]
    result = plan(
        squad,
        market,
        _history(p50=100_000),
        cash=10_000_000,
        round_eve=False,
        negative_limit=0,
        rules=RULES,
        already_bid={70},
    )
    assert result.buys == []
    assert [why for _, why in result.skipped] == ["plantilla llena"]


def test_a_new_keeper_who_drops_out_of_the_eleven_is_not_sold_days_after_signing():
    """Signed to replace the old keeper, then injured for a week: the eleven
    picks the old one, and the hold keeps the new one from going cheap."""
    injured = dict(_player(2, 700, GK), acq_date=86_400 * 9)
    injured["jp_player"] = {**injured["jp_player"], "status": "injured"}
    squad = _eleven() + [injured]
    rules = Rules(**{**RULES.__dict__, "hold_days": 14})
    result = plan(
        squad,
        [],
        _flat(),
        cash=0,
        round_eve=False,
        negative_limit=0,
        rules=rules,
        now=86_400 * 10,
    )
    assert result.sells == []


def test_the_old_keeper_is_kept_while_the_new_one_is_clause_protected():
    """The new keeper cannot be claused for his first two weeks, so the old
    one costs nothing as cover until then — and a clause on him pays."""
    new = dict(_player(2, 900, GK), acq_date=int(NOW - 3 * DAY))
    old = dict(_player(1, 400, GK), acq_date=int(NOW - 100 * DAY))
    squad = [old] + _eleven()[1:] + [new]
    result = plan(
        squad,
        [],
        _flat(),
        cash=0,
        round_eve=False,
        negative_limit=0,
        rules=HOLD,
        now=NOW,
    )
    assert result.sells == []
    ((_, why),) = [(r, w) for r, w in result.held if r["bw_id"] == 1]
    assert "portero nuevo" in why

    later = NOW + 12 * DAY
    result = plan(
        squad,
        [],
        _flat(),
        cash=0,
        round_eve=False,
        negative_limit=0,
        rules=HOLD,
        now=later,
    )
    assert [m.row["bw_id"] for m in result.sells] == [1]


def test_the_covering_keeper_is_kept_even_while_his_price_falls():
    new = dict(_player(2, 900, GK), acq_date=int(NOW - 3 * DAY))
    old = dict(_player(1, 400, GK), acq_date=int(NOW - 100 * DAY))
    squad = [old] + _eleven()[1:] + [new]
    result = plan(
        squad,
        [],
        _history(p1=-50_000),
        cash=0,
        round_eve=False,
        negative_limit=0,
        rules=HOLD,
        now=NOW,
    )
    assert result.sells == []
