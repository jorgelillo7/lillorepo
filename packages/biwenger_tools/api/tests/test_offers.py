"""Tests for `api/logic/offers` — recommendation algorithm + tier mapping
+ run_offers_inbox orchestration. The route wiring is tested in
`test_routes.py`."""

from unittest.mock import MagicMock, patch

from packages.biwenger_tools.api.logic import auto_bid as ab
from packages.biwenger_tools.api.logic import offers


def _p(target):
    return f"packages.biwenger_tools.api.logic.offers.{target}"


# --- Recommendation algorithm — one case per rule branch -------------------


def test_recommend_rejects_star_player():
    """T1 (SF >= TIER_ALL_IN_MIN) is never sold by default."""
    rec, reasons = offers._recommend(
        sf=ab.TIER_ALL_IN_MIN + 50, roi_pct=20.0, vs_market_pct=0.0, is_starter=True
    )
    assert rec == offers.REC_REJECT
    assert any("estrella" in r.lower() or "titular fijo" in r.lower() for r in reasons)


def test_recommend_rejects_t2_starter():
    """T2 + is_starter → still RECHAZAR (titular fijo)."""
    rec, _ = offers._recommend(
        sf=ab.TIER_T2_MIN + 10, roi_pct=10.0, vs_market_pct=5.0, is_starter=True
    )
    assert rec == offers.REC_REJECT


def test_recommend_star_with_indecent_offer_becomes_doubtful():
    """Override: T1 player with an offer ≥ STAR_OVERRIDE_OVER_MARKET_PCT → DUDOSO."""
    rec, _ = offers._recommend(
        sf=ab.TIER_ALL_IN_MIN + 50,
        roi_pct=50.0,
        vs_market_pct=offers.STAR_OVERRIDE_OVER_MARKET_PCT + 1,
        is_starter=True,
    )
    assert rec == offers.REC_DOUBTFUL


def test_recommend_accepts_bench_warmer_with_profit():
    """Descarte / fondo de armario con plusvalía → ACEPTAR."""
    rec, reasons = offers._recommend(
        sf=100, roi_pct=10.0, vs_market_pct=-5.0, is_starter=False
    )
    assert rec == offers.REC_ACCEPT
    assert any("plusval" in r.lower() or "fondo" in r.lower() for r in reasons)


def test_recommend_accepts_offer_clearly_above_market():
    """Any tier, offer well above cf-base → ACEPTAR."""
    rec, _ = offers._recommend(
        sf=ab.TIER_T3_MIN + 20,
        roi_pct=None,
        vs_market_pct=offers.ACCEPT_OVER_MARKET_PCT + 1,
        is_starter=False,
    )
    assert rec == offers.REC_ACCEPT


def test_recommend_rejects_offer_clearly_below_market():
    """Offer well under cf-base → RECHAZAR (sell publicly)."""
    rec, _ = offers._recommend(
        sf=ab.TIER_T3_MIN + 20,
        roi_pct=None,
        vs_market_pct=offers.REJECT_UNDER_MARKET_PCT - 1,
        is_starter=False,
    )
    assert rec == offers.REC_REJECT


def test_recommend_doubtful_for_rotation_with_fair_offer():
    """T3 (rotación) with offer within +/- a few % → DUDOSO."""
    rec, _ = offers._recommend(
        sf=ab.TIER_T3_MIN + 10, roi_pct=5.0, vs_market_pct=2.0, is_starter=False
    )
    assert rec == offers.REC_DOUBTFUL


def test_recommend_catchall_returns_doubtful():
    """T4/no-tier with ambiguous market data → DUDOSO (catch-all)."""
    rec, _ = offers._recommend(
        sf=ab.TIER_T4_MIN, roi_pct=None, vs_market_pct=None, is_starter=False
    )
    assert rec == offers.REC_DOUBTFUL


# --- Tier label boundaries -------------------------------------------------


def test_tier_label_boundaries():
    assert "T1" in offers._tier_label(ab.TIER_ALL_IN_MIN)
    assert "T2" in offers._tier_label(ab.TIER_T2_MIN)
    assert "T3" in offers._tier_label(ab.TIER_T3_MIN)
    assert "T4" in offers._tier_label(ab.TIER_T4_MIN)
    assert "Descarte" in offers._tier_label(ab.TIER_T4_MIN - 1)


# --- run_offers_inbox: silent on empty + sends per offer -------------------


def _ctx_with_offers(returned_offers):
    biwenger = MagicMock()
    biwenger.user_id = 1
    biwenger.get_received_offers.return_value = returned_offers
    biwenger.get_manager_squad.return_value = []

    from packages.biwenger_tools.api.logic.orchestration import OrchestratorContext

    return OrchestratorContext(
        biwenger=biwenger,
        biwenger_players={
            26566: {
                "id": 26566,
                "name": "Carlos Romero",
                "position": 2,
                "price": 1_000_000,
            }
        },
        jp_index={"by_name": {}, "by_slug": {}},
    )


def test_run_offers_inbox_silent_when_empty_default():
    """Default (digest mode): empty inbox → no Telegram send."""
    ctx = _ctx_with_offers([])
    with patch(_p("require_telegram"), return_value=("tok", "chat")), patch(
        _p("send_telegram_message")
    ) as mock_send:
        result = offers.run_offers_inbox(ctx)
    mock_send.assert_not_called()
    assert result == {"sent": 0, "offers": 0}


def test_run_offers_inbox_notifies_when_empty_and_requested():
    """On-demand mode (notify_empty=True): empty inbox → "📭 Sin ofertas
    pendientes" so the user gets a reply instead of staring at "procesando…"."""
    ctx = _ctx_with_offers([])
    with patch(_p("require_telegram"), return_value=("tok", "chat")), patch(
        _p("send_telegram_message")
    ) as mock_send:
        result = offers.run_offers_inbox(ctx, notify_empty=True)
    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs.get("text", "")
    assert "Sin ofertas" in text
    assert result == {"sent": 1, "offers": 0}


def test_run_offers_inbox_sends_one_message_per_offer():
    fake_offer = {
        "id": 99,
        "amount": 100_000,
        "status": "waiting",
        "type": "purchase",
        "from": None,
        "to": {"id": 1},
        "requestedPlayers": [26566],
        "until": 1782450000,
    }
    ctx = _ctx_with_offers([fake_offer, fake_offer])
    with patch(_p("require_telegram"), return_value=("tok", "chat")), patch(
        _p("send_telegram_message")
    ) as mock_send, patch(_p("_starter_ids"), return_value=set()):
        result = offers.run_offers_inbox(ctx)
    assert mock_send.call_count == 2
    assert result == {"sent": 2, "offers": 2}
    # The keyboard must carry the o:a/r/i callbacks for the offer id.
    markup = mock_send.call_args.kwargs.get("reply_markup")
    callbacks = [
        btn["callback_data"] for row in markup["inline_keyboard"] for btn in row
    ]
    assert callbacks == ["o:a:99", "o:r:99", "o:i:99"]


def test_run_offers_inbox_skips_malformed_offer():
    """An offer with empty `requestedPlayers` must be skipped, not crash."""
    bad = {
        "id": 100,
        "amount": 0,
        "status": "waiting",
        "type": "purchase",
        "from": None,
        "to": {"id": 1},
        "requestedPlayers": [],
    }
    ctx = _ctx_with_offers([bad])
    with patch(_p("require_telegram"), return_value=("tok", "chat")), patch(
        _p("send_telegram_message")
    ) as mock_send, patch(_p("_starter_ids"), return_value=set()):
        result = offers.run_offers_inbox(ctx)
    mock_send.assert_not_called()
    assert result == {"sent": 0, "offers": 1}


# --- run_offer_decision: forwards + posts confirmation ---------------------


def test_run_offer_decision_invalid_raises():
    import pytest

    with pytest.raises(ValueError):
        offers.run_offer_decision(offer_id=1, decision="bogus")


def test_run_offer_decision_forwards_to_sdk_and_notifies():
    biwenger = MagicMock()
    biwenger.decide_offer.return_value = {"id": 1, "status": "processed"}
    with patch(_p("build_biwenger_session"), return_value=biwenger), patch(
        _p("require_telegram"), return_value=("tok", "chat")
    ), patch(_p("send_telegram_message")) as mock_send:
        result = offers.run_offer_decision(offer_id=1, decision="accepted")

    biwenger.decide_offer.assert_called_once_with(1, "accepted")
    assert result["final_status"] == "processed"
    text = mock_send.call_args.kwargs.get("text", "")
    assert "Aceptada" in text
    assert "processed" in text
