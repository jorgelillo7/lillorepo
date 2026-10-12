"""Tests for `price_history`: daily prices and the streaks read off them."""

from packages.biwenger_tools.api.logic.price_history import prices_of, streak


def test_prices_keep_every_priced_player_by_id():
    players = {
        1: {"id": 1, "price": 2_000_000},
        2: {"id": 2, "price": 0},
        3: {"id": 3},
    }
    assert prices_of(players) == {1: 2_000_000}


def test_a_rise_on_each_of_the_last_three_days_is_a_streak_of_three():
    history = [{7: 100}, {7: 110}, {7: 120}, {7: 130}]
    assert streak(history, 7) == 3


def test_falls_count_negative():
    history = [{7: 130}, {7: 120}, {7: 110}]
    assert streak(history, 7) == -2


def test_only_the_run_that_ends_today_counts():
    """Up, up, then down: today's direction is down, for one day."""
    history = [{7: 100}, {7: 110}, {7: 120}, {7: 115}]
    assert streak(history, 7) == -1


def test_a_flat_day_ends_the_streak():
    history = [{7: 100}, {7: 110}, {7: 110}]
    assert streak(history, 7) == 0


def test_a_day_without_the_player_ends_the_streak_rather_than_bridging_it():
    """A gap is not a rise: the player may have left the competition's list."""
    history = [{7: 100}, {7: 110}, {}, {7: 130}, {7: 140}]
    assert streak(history, 7) == 1


def test_too_little_history_is_no_streak():
    assert streak([{7: 100}], 7) == 0
    assert streak([], 7) == 0
