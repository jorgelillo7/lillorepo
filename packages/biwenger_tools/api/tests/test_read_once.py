"""Unit tests for `api/logic/read_once` — one digest, one read of each thing."""

from unittest.mock import MagicMock

import pytest

from packages.biwenger_tools.api.logic.read_once import ReadOnce


def _client():
    biwenger = MagicMock()
    biwenger.user_id = 7
    biwenger.get_round.side_effect = lambda round_id=None: {"id": round_id or 10}
    biwenger.get_manager_squad.return_value = [{"id": 1}]
    biwenger.get_market_players.return_value = [{"id": 2}]
    return biwenger


def test_each_round_is_read_once():
    biwenger = _client()
    reads = ReadOnce(biwenger)

    assert reads.get_round() == {"id": 10}
    reads.get_round()
    reads.get_round(11)
    reads.get_round(11)

    assert biwenger.get_round.call_count == 2


def test_squad_and_market_are_read_once_across_lineup_and_bids():
    biwenger = _client()
    reads = ReadOnce(biwenger)

    reads.get_manager_squad("u/{manager_id}", 7)
    reads.get_market_players("m")
    reads.set_lineup([1], 1, "4-4-2")
    reads.place_market_bid(player_id=2, amount=1)
    reads.list_squad_for_sale(100)
    reads.get_manager_squad("u/{manager_id}", 7)

    assert biwenger.get_manager_squad.call_count == 1
    biwenger.place_market_bid.assert_called_once_with(player_id=2, amount=1)


@pytest.mark.parametrize(
    "write", ["decide_offer", "place_clausulazo", "transfer_player", "release_player"]
)
def test_a_write_that_can_change_the_squad_forces_a_fresh_read(write):
    """The live trader accepts an offer; the offers step after it must see
    the squad without the player just sold."""
    biwenger = _client()
    reads = ReadOnce(biwenger)

    reads.get_manager_squad("u/{manager_id}", 7)
    getattr(reads, write)(1, "accepted")
    reads.get_manager_squad("u/{manager_id}", 7)

    assert biwenger.get_manager_squad.call_count == 2


def test_a_write_that_failed_still_forces_a_fresh_read():
    """A write that raised may have landed anyway."""
    biwenger = _client()
    biwenger.decide_offer.side_effect = RuntimeError("timeout")
    reads = ReadOnce(biwenger)

    reads.get_manager_squad("u/{manager_id}", 7)
    with pytest.raises(RuntimeError):
        reads.decide_offer(1, "accepted")
    reads.get_manager_squad("u/{manager_id}", 7)

    assert biwenger.get_manager_squad.call_count == 2


def test_listing_the_squad_for_sale_drops_the_market():
    biwenger = _client()
    reads = ReadOnce(biwenger)

    reads.get_market_players("m")
    reads.list_squad_for_sale(100)
    reads.get_market_players("m")

    assert biwenger.get_market_players.call_count == 2


def test_reads_that_follow_writes_are_never_kept():
    """Pending bids, offers, cash and the saved lineup are each read after a
    write in the same digest."""
    biwenger = _client()
    reads = ReadOnce(biwenger)

    for _ in range(2):
        reads.get_my_pending_bids("m")
        reads.get_received_offers()
        reads.get_account_state()
        reads.get_current_lineup()

    assert biwenger.get_my_pending_bids.call_count == 2
    assert biwenger.get_received_offers.call_count == 2
    assert biwenger.get_account_state.call_count == 2
    assert biwenger.get_current_lineup.call_count == 2


def test_a_failed_or_empty_read_is_not_kept():
    """A step that reads after another one failed gets its own try, and an
    empty calendar still reads as unreadable."""
    biwenger = _client()
    biwenger.get_round.side_effect = [RuntimeError("cf down"), {}, {"id": 10}]
    reads = ReadOnce(biwenger)

    with pytest.raises(RuntimeError):
        reads.get_round()
    assert reads.get_round() == {}
    assert reads.get_round() == {"id": 10}
    reads.get_round()

    assert biwenger.get_round.call_count == 3


def test_attributes_pass_through():
    biwenger = _client()
    assert ReadOnce(biwenger).user_id == 7
