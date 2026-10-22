"""Tests for `trader_run`: the digest's trading step, wired at its boundaries."""

from unittest.mock import MagicMock

from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import trader_run

_NOW = 1_791_792_000  # Monday 12/10/2026 10:00 Madrid


class _Store:
    def __init__(self, history):
        self.history = history
        self.written = []

    def write(self, day, prices):
        self.written.append((day.isoformat(), prices))

    def recent(self, days):
        return self.history[-days:]


def _ctx(cash=5_000_000, pending=(), inbox=()):
    ctx = MagicMock()
    ctx.biwenger_players = {7: {"id": 7, "price": 2_000_000}}
    ctx.biwenger.get_account_state.return_value = {"cash": cash}
    ctx.biwenger.get_my_pending_bids.return_value = list(pending)
    ctx.biwenger.get_received_offers.return_value = list(inbox)
    ctx.biwenger.decide_offer.return_value = {"status": "processed"}
    return ctx


def _run(monkeypatch, mode, history):
    store, sent = _Store(history), []
    monkeypatch.setattr(trader_run, "price_history_store", store)
    monkeypatch.setattr(
        trader_run, "send_telegram_message", lambda **kw: sent.append(kw["text"])
    )
    monkeypatch.setattr(config, "TRADER_MODE", mode)
    ctx = _ctx()
    result = trader_run.run(ctx, [], [], [], token="t", chat_id="c", now=_NOW)
    return result, store, sent, ctx


def test_a_dry_run_stores_the_day_plans_and_reports_without_touching_biwenger(
    monkeypatch,
):
    result, store, sent, ctx = _run(monkeypatch, "dry_run", [{}] * 4)
    assert store.written == [("2026-10-12", {7: 2_000_000})]
    assert result["mode"] == "dry_run"
    assert len(sent) == 1 and "simulación" in sent[0]
    ctx.biwenger.place_market_bid.assert_not_called()
    ctx.biwenger.decide_offer.assert_not_called()
    ctx.biwenger.list_squad_for_sale.assert_not_called()


def test_off_still_keeps_the_price_history_but_plans_nothing(monkeypatch):
    result, store, sent, _ = _run(monkeypatch, "off", [{}] * 4)
    assert store.written and sent == []
    assert result == {"mode": "off"}


def test_short_history_is_said_rather_than_read_as_a_quiet_market(monkeypatch):
    """With two days stored no three-day rise can exist yet."""
    result, _, sent, _ = _run(monkeypatch, "dry_run", [{}] * 2)
    assert result["history_days"] == 2
    assert "2 días de precios" in sent[0]


# --- live: what reaches Biwenger, once ----------------------------------------

from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID  # noqa: E402


def _player(bw_id, sf, position, price=2_000_000):
    return {
        "bw_id": bw_id,
        "name": f"P{bw_id}",
        "price": price,
        "position_id": position,
        "alt_positions": [],
        "jp_player": {
            "status": "ok",
            "nextMatch": {"status": "pending", "playerInLineup": True},
            "predict": [{"type": 2, "rate": sf}],
        },
    }


def _squad():
    """A 4-4-2 eleven plus a benched defender, P40."""
    return (
        [_player(1, 400, GK)]
        + [_player(10 + i, 400, DEF) for i in range(4)]
        + [_player(20 + i, 400, MID) for i in range(4)]
        + [_player(30 + i, 400, FWD) for i in range(2)]
        + [_player(40, 100, DEF)]
    )


def _history():
    """P40 falls 3 days, market player P50 rises 3."""
    days = []
    for day in range(4):
        prices = {i: 2_000_000 for i in range(1, 100)}
        prices[40] = 2_300_000 - 100_000 * day
        prices[50] = 1_700_000 + 100_000 * day
        days.append(prices)
    return days


def _live(monkeypatch, ctx):
    sent = []
    monkeypatch.setattr(trader_run, "price_history_store", _Store(_history()))
    monkeypatch.setattr(
        trader_run, "send_telegram_message", lambda **kw: sent.append(kw["text"])
    )
    monkeypatch.setattr(config, "TRADER_MODE", "live")
    monkeypatch.setattr(config, "TRADER_MIN_SQUAD", 11)
    result = trader_run.run(
        ctx,
        _squad(),
        [_player(50, 500, MID)],
        [{"status": "pending", "games": [{"date": _NOW + 5 * 86400}]}],
        token="t",
        chat_id="c",
        now=_NOW,
    )
    return result, sent


def _offer(offer_id, player, amount):
    return {"id": offer_id, "amount": amount, "requestedPlayers": [player]}


def test_live_sells_the_faller_lists_the_squad_and_bids_on_the_riser(monkeypatch):
    ctx = _ctx(cash=0, inbox=[_offer(9, 40, 2_000_000), _offer(8, 20, 9_000_000)])
    result, sent = _live(monkeypatch, ctx)

    ctx.biwenger.decide_offer.assert_called_once_with(9, "accepted")
    ctx.biwenger.list_squad_for_sale.assert_called_once_with(config.TRADER_LIST_PERCENT)
    ctx.biwenger.place_market_bid.assert_called_once_with(
        player_id=50, amount=2_060_000
    )
    assert result["sold"] == [40] and result["bid"] == [50]
    assert "simulación" not in sent[0] and "Vendo" in sent[0]


def test_a_retried_run_does_not_bid_again_on_a_player_it_already_bid_on(
    monkeypatch,
):
    ctx = _ctx(
        cash=5_000_000, pending=[{"amount": 2_060_000, "requestedPlayers": [50]}]
    )
    _live(monkeypatch, ctx)
    ctx.biwenger.place_market_bid.assert_not_called()


def test_a_refused_bid_is_sent_once_and_the_run_carries_on(monkeypatch):
    ctx = _ctx(cash=5_000_000)
    ctx.biwenger.place_market_bid.side_effect = RuntimeError("409")
    result, sent = _live(monkeypatch, ctx)

    assert ctx.biwenger.place_market_bid.call_count == 1
    assert result["bid"] == []
    assert len(sent) == 1


def test_a_sale_biwenger_did_not_settle_buys_nothing_with_its_money(monkeypatch):
    """Only money actually received pays for a bid: with no cash, an accept
    that fails leaves nothing to bid with on a round's eve."""
    ctx = _ctx(cash=0, inbox=[_offer(9, 40, 2_000_000)])
    ctx.biwenger.decide_offer.side_effect = RuntimeError("410 gone")
    monkeypatch.setattr(trader_run.trader, "round_eve", lambda rounds, now: True)
    result, _ = _live(monkeypatch, ctx)

    assert ctx.biwenger.decide_offer.call_count == 1
    assert result["sold"] == []
    ctx.biwenger.place_market_bid.assert_not_called()


def test_a_planned_sell_without_an_offer_waits_listed(monkeypatch):
    ctx = _ctx(cash=5_000_000)
    result, sent = _live(monkeypatch, ctx)
    ctx.biwenger.decide_offer.assert_not_called()
    assert result["sold"] == []
    assert "sin oferta" in sent[0]


def test_the_summary_names_everyone_the_trader_is_selling(monkeypatch):
    """Sold or still listed, they are gone as far as the offers step is
    concerned; it reads them from here."""
    ctx = _ctx(cash=5_000_000)
    result, _ = _live(monkeypatch, ctx)
    assert result["selling"] == [40]
