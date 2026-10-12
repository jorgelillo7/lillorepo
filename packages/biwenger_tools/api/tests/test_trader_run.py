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


def _ctx(cash=5_000_000):
    ctx = MagicMock()
    ctx.biwenger_players = {7: {"id": 7, "price": 2_000_000}}
    ctx.biwenger.get_account_state.return_value = {"cash": cash}
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


def test_off_still_keeps_the_price_history_but_plans_nothing(monkeypatch):
    result, store, sent, _ = _run(monkeypatch, "off", [{}] * 4)
    assert store.written and sent == []
    assert result == {"mode": "off"}


def test_short_history_is_said_rather_than_read_as_a_quiet_market(monkeypatch):
    """With two days stored no three-day rise can exist yet."""
    result, _, sent, _ = _run(monkeypatch, "dry_run", [{}] * 2)
    assert result["history_days"] == 2
    assert "2 días de precios" in sent[0]
