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
    """T2 + is_starter → RECHAZAR (titular fijo)."""
    rec, _ = offers._recommend(
        sf=ab.TIER_T2_MIN + 10, roi_pct=10.0, vs_market_pct=5.0, is_starter=True
    )
    assert rec == offers.REC_REJECT


def test_recommend_rejects_t2_even_when_not_marked_as_starter():
    """User feedback 25/06: T2 jugador titular fijo, ofrecen 7M tras pagar 14M
    (-50% ROI, vs_market 0%), is_starter=False porque pick_lineup le excluyó
    al no tener SF para esta jornada. Antes caía en DUDOSO; ahora RECHAZA
    igualmente porque T2 ya es señal suficiente."""
    rec, _ = offers._recommend(
        sf=ab.TIER_T2_MIN + 10, roi_pct=-50.0, vs_market_pct=0.0, is_starter=False
    )
    assert rec == offers.REC_REJECT


def test_recommend_rejects_useful_player_with_heavy_loss():
    """T3 (rotación) con pérdida >= 25% sobre lo pagado → RECHAZAR.
    Loss-aversion rule: no aceptes pérdidas grandes en jugadores útiles."""
    rec, reasons = offers._recommend(
        sf=ab.TIER_T3_MIN + 50,
        roi_pct=offers.REJECT_LOSS_PCT - 5,  # peor que -25%
        vs_market_pct=-5.0,
        is_starter=False,
    )
    assert rec == offers.REC_REJECT
    assert any("pérdida" in r.lower() for r in reasons)


def test_recommend_loss_aversion_overridden_by_strong_market_premium():
    """Excepción a la loss-aversion: si el mercado paga sobre cf-base
    aunque tú pierdas mucho vs compra, ACEPTAR (al menos recuperas lo
    que el mercado dice que vale + extra)."""
    rec, reasons = offers._recommend(
        sf=ab.TIER_T3_MIN + 50,
        roi_pct=-40.0,
        vs_market_pct=offers.ACCEPT_OVER_MARKET_PCT + 5,  # +20% sobre cf-base
        is_starter=False,
    )
    assert rec == offers.REC_ACCEPT
    assert any("compensa" in r.lower() for r in reasons)


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


# --- Squad depth: what the eleven loses if he goes -------------------------


def test_recommend_rejects_starter_whose_replacement_cannot_cover():
    """The reported case, with its real numbers.

    Dmitrovic — first-choice keeper, SF 404, bought at 3.97M, offered 4.77M
    (+20% ROI, +2% over cf-base), the only other keeper on the books
    projecting 12. Every financial signal says "fine offer", his SF alone
    says "rotación", and selling would have left the goal to a substitute who
    does not play. Scored DUDOSO — `is_starter` was passed to `_recommend`
    and read by no branch in it.
    """
    rec, reasons = offers._recommend(
        sf=404,
        roi_pct=20.0,
        vs_market_pct=2.0,
        is_starter=True,
        xi_loss=390,
        breaks_xi=False,
    )
    assert rec == offers.REC_REJECT
    assert any("390" in r for r in reasons)


def test_recommend_rejects_when_selling_breaks_the_eleven():
    """No valid XI without him → refuse regardless of the money.

    An empty slot is a flat -4 on the round, so there is no offer that
    makes this a good trade.
    """
    rec, reasons = offers._recommend(
        sf=404,
        roi_pct=200.0,
        vs_market_pct=50.0,
        is_starter=True,
        xi_loss=None,
        breaks_xi=True,
    )
    assert rec == offers.REC_REJECT
    assert any("11 legal" in r for r in reasons)


def test_recommend_downgrades_irreplaceable_starter_on_an_indecent_offer():
    """Above the star-override bar the depth rule steps back to DUDOSO —
    the user decides whether the money beats the hole."""
    rec, _ = offers._recommend(
        sf=404,
        roi_pct=20.0,
        vs_market_pct=offers.STAR_OVERRIDE_OVER_MARKET_PCT + 5,
        is_starter=True,
        xi_loss=390,
        breaks_xi=False,
    )
    assert rec == offers.REC_DOUBTFUL


def test_recommend_lets_replaceable_starter_be_sold():
    """Same SF, same money, but the squad covers the position: the depth
    rule must not fire, or it would block every sale the user wants."""
    rec, reasons = offers._recommend(
        sf=404,
        roi_pct=20.0,
        vs_market_pct=2.0,
        is_starter=True,
        xi_loss=5,
        breaks_xi=False,
    )
    assert rec == offers.REC_DOUBTFUL
    assert any("recambio" in r for r in reasons)


def test_recommend_without_depth_signal_keeps_old_behaviour():
    """The signal is best-effort — a Biwenger/optimizer failure must leave
    the money rules exactly as they were, not change the verdict."""
    rec, _ = offers._recommend(
        sf=404, roi_pct=20.0, vs_market_pct=2.0, is_starter=True, xi_loss=None
    )
    assert rec == offers.REC_DOUBTFUL


def _sf_jp(rate):
    return {"predict": [{"type": 2, "rate": rate}]}


def _squad_with_two_keepers():
    """A fieldable squad: two keepers and thirteen outfielders."""
    squad = [
        {"bw_id": 1, "name": "Titular POR", "position_id": 1, "jp_player": _sf_jp(402)},
        {"bw_id": 2, "name": "Fortuño", "position_id": 1, "jp_player": _sf_jp(12)},
    ]
    for i in range(3, 16):
        squad.append(
            {
                "bw_id": i,
                "name": f"J{i}",
                "position_id": 2 + (i % 3),
                "jp_player": _sf_jp(300 + i),
            }
        )
    return squad


def test_xi_impact_prices_a_scarce_position_higher_than_a_covered_one():
    """The whole point of running the optimizer instead of comparing SFs:
    the same projection is worth different amounts at different positions."""
    squad = _squad_with_two_keepers()
    base = offers._xi_baseline(squad)
    impact = offers._xi_impact(squad, 1, base)
    assert impact["breaks_xi"] is False
    # Losing the keeper drops the eleven to a 12-SF substitute.
    assert impact["xi_loss"] >= 300


def test_xi_impact_names_the_player_who_actually_comes_in():
    """The replacement is the man who enters the eleven, not the best squad
    member at that position — that one is usually already on the pitch, and
    naming him printed "tu 11 pierde 95 SF" above a current starter's name."""
    squad = _squad_with_two_keepers()
    base = offers._xi_baseline(squad)
    impact = offers._xi_impact(squad, 1, base)
    assert impact["replacement_name"] == "Fortuño"
    assert impact["replacement_sf"] == 12
    assert impact["replacement_name"] not in [
        row["name"] for row in squad if row["bw_id"] in base["starter_ids"]
    ]


def test_xi_impact_flags_the_squad_that_cannot_field_an_eleven_without_him():
    """One keeper, and he is the one under offer."""
    squad = [
        {"bw_id": 1, "name": "Único POR", "position_id": 1, "jp_player": _sf_jp(4)}
    ]
    for i in range(2, 16):
        squad.append(
            {
                "bw_id": i,
                "name": f"J{i}",
                "position_id": 2 + (i % 3),
                "jp_player": _sf_jp(300),
            }
        )
    base = offers._xi_baseline(squad)
    assert offers._xi_impact(squad, 1, base)["breaks_xi"] is True


def test_xi_impact_survives_an_optimizer_failure():
    """Best-effort: the offer message must still go out."""
    base = {"total_sf": 1, "starter_ids": set()}
    with patch(_p("lineup.xi_snapshot"), side_effect=RuntimeError("boom")):
        impact = offers._xi_impact([{"bw_id": 1}], 1, base)
    assert impact["xi_loss"] is None and impact["breaks_xi"] is False


def test_xi_impact_without_a_baseline_reports_nothing():
    assert offers._xi_impact([{"bw_id": 1}], 1, None)["xi_loss"] is None


def test_xi_impact_respects_the_deadline():
    """Past the budget the signal degrades instead of eating the digest SLO."""
    import time

    squad = _squad_with_two_keepers()
    base = offers._xi_baseline(squad)
    impact = offers._xi_impact(squad, 1, base, deadline=time.monotonic() - 1)
    assert impact == offers._NO_XI_IMPACT


def test_a_non_starter_offer_never_pays_for_the_search():
    """The depth rules all require `is_starter`, so for anyone else the solve
    cannot change the verdict — and it costs ~0.65-3 s each."""
    with patch(_p("_xi_impact")) as impact:
        offers._score_offer(
            {"id": 1, "requestedPlayers": [{"id": 99}], "amount": 1_000_000},
            MagicMock(biwenger_players={}, jp_index={}),
            {},
            starter_ids=set(),
            my_team=[],
            xi_base={"total_sf": 1, "starter_ids": set()},
        )
    impact.assert_not_called()


def test_a_starter_offer_does_pay_for_the_search():
    with patch(_p("_xi_impact"), return_value=dict(offers._NO_XI_IMPACT)) as impact:
        offers._score_offer(
            {"id": 1, "requestedPlayers": [{"id": 99}], "amount": 1_000_000},
            MagicMock(biwenger_players={}, jp_index={}),
            {},
            starter_ids={99},
            my_team=[],
            xi_base={"total_sf": 1, "starter_ids": set()},
        )
    impact.assert_called_once()


def test_xi_baseline_swallows_an_optimizer_failure():
    with patch(_p("lineup.xi_snapshot"), side_effect=RuntimeError("boom")):
        assert offers._xi_baseline([{"bw_id": 1}]) is None


# --- Tier label boundaries -------------------------------------------------


def test_tier_label_boundaries():
    """Each band names a *projection*, never a squad role.

    These read "Titular fijo" / "Rotación" / "Fondo de armario" — `auto_bid`'s
    acquisition tiers — until a first-choice goalkeeper projecting 404 came
    back labelled "⭐ Rotación" and was recommended for sale. Squad role is
    now its own line, computed from the squad rather than from one number.
    """
    assert "Proyección top" in offers._tier_label(ab.TIER_ALL_IN_MIN)
    assert "Proyección alta" in offers._tier_label(ab.TIER_T2_MIN)
    assert "Proyección media" in offers._tier_label(ab.TIER_T3_MIN)
    assert "Proyección baja" in offers._tier_label(ab.TIER_T4_MIN)
    assert "Sin proyección" in offers._tier_label(ab.TIER_T4_MIN - 1)
    for sf in (ab.TIER_ALL_IN_MIN, ab.TIER_T3_MIN, ab.TIER_T4_MIN - 1):
        label = offers._tier_label(sf)
        assert "Titular" not in label and "Rotación" not in label
        assert str(sf) in label


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


def test_run_offers_inbox_sends_one_message_per_actionable_offer():
    """One message per offer *worth deciding on*.

    It used to be one per offer full stop, which is what made listing a squad
    on the market arrive as fifteen notifications. These two score RECHAZAR
    (a 100K offer on a 1M player), so they collapse into a single digest —
    `test_an_actionable_offer_still_arrives_with_its_buttons` covers the
    other side.
    """
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
    assert mock_send.call_count == 1
    assert result == {"sent": 1, "offers": 2, "actionable": 0, "muted": 2}

    # With muting off, both arrive individually and carry their callbacks.
    with patch.object(offers.config, "OFFERS_MUTE_REJECTED", False), patch(
        _p("require_telegram"), return_value=("tok", "chat")
    ), patch(_p("send_telegram_message")) as mock_send, patch(
        _p("_starter_ids"), return_value=set()
    ):
        result = offers.run_offers_inbox(ctx)
    assert mock_send.call_count == 2
    assert result == {"sent": 2, "offers": 2, "actionable": 2, "muted": 0}
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
    assert result == {"sent": 0, "offers": 1, "actionable": 0, "muted": 0}


# --- run_offer_decision: forwards + posts confirmation ---------------------


def test_run_offer_decision_invalid_raises():
    import pytest

    with pytest.raises(ValueError):
        offers.run_offer_decision(offer_id=1, decision="bogus")


def test_starter_ids_pulls_from_biwenger_lineup_not_pick_lineup():
    """`_starter_ids` MUST hit `BiwengerClient.get_current_lineup_player_ids()`
    (the real lineup the user has saved on Biwenger) instead of computing
    pick_lineup's optimal 11. Regression for 25/06: user only had 1 valid
    player + 10 empty slots in his lineup; pick_lineup returned None, and
    is_starter went False for everyone — including the real starter."""
    biwenger = MagicMock()
    biwenger.user_id = 1
    biwenger.get_current_lineup_player_ids.return_value = {42, 99}

    from packages.biwenger_tools.api.logic.orchestration import OrchestratorContext

    ctx = OrchestratorContext(
        biwenger=biwenger,
        biwenger_players={},
        jp_index={"by_name": {}, "by_slug": {}},
    )

    assert offers._starter_ids(ctx) == {42, 99}
    biwenger.get_current_lineup_player_ids.assert_called_once()


def test_starter_ids_swallows_sdk_failure():
    """If the lineup fetch blows up the recommendation must still work,
    just without the is_starter signal."""
    biwenger = MagicMock()
    biwenger.user_id = 1
    biwenger.get_current_lineup_player_ids.side_effect = RuntimeError("boom")

    from packages.biwenger_tools.api.logic.orchestration import OrchestratorContext

    ctx = OrchestratorContext(
        biwenger=biwenger,
        biwenger_players={},
        jp_index={"by_name": {}, "by_slug": {}},
    )

    assert offers._starter_ids(ctx) == set()


def test_run_offer_decision_stays_quiet_when_biwenger_agrees():
    """It used to send "Oferta Aceptada · id 1657307609 · estado final:
    processed" — a message naming neither the player nor the price, so the
    reader had to correlate an id against the offer above it. The bot now
    writes the verdict onto the offer message itself, so repeating it here
    was noise."""
    biwenger = MagicMock()
    biwenger.decide_offer.return_value = {"id": 1, "status": "processed"}
    with patch(_p("build_biwenger_session"), return_value=biwenger), patch(
        _p("require_telegram"), return_value=("tok", "chat")
    ), patch(_p("send_telegram_message")) as mock_send:
        result = offers.run_offer_decision(offer_id=1, decision="accepted")

    biwenger.decide_offer.assert_called_once_with(1, "accepted")
    assert result["final_status"] == "processed"
    assert result["sent"] == 0
    mock_send.assert_not_called()


def test_run_offer_decision_speaks_up_when_biwenger_settles_elsewhere():
    """The one case the old message existed to catch, now the only case it
    fires on: we asked to accept and Biwenger did something else."""
    biwenger = MagicMock()
    biwenger.decide_offer.return_value = {"id": 1, "status": "expired"}
    with patch(_p("build_biwenger_session"), return_value=biwenger), patch(
        _p("require_telegram"), return_value=("tok", "chat")
    ), patch(_p("send_telegram_message")) as mock_send:
        result = offers.run_offer_decision(offer_id=1, decision="accepted")

    assert result["sent"] == 1
    text = mock_send.call_args.kwargs.get("text", "")
    assert "expired" in text and "accepted" in text


def test_a_rejection_settling_as_rejected_is_not_a_surprise():
    """An accept settles as `processed`, a reject stays `rejected` — the two
    have different expected outcomes and neither should warn."""
    biwenger = MagicMock()
    biwenger.decide_offer.return_value = {"id": 1, "status": "rejected"}
    with patch(_p("build_biwenger_session"), return_value=biwenger), patch(
        _p("require_telegram"), return_value=("tok", "chat")
    ), patch(_p("send_telegram_message")) as mock_send:
        result = offers.run_offer_decision(offer_id=1, decision="rejected")

    assert result["sent"] == 0
    mock_send.assert_not_called()


# --- Muting the offers that were already answered -------------------------


def _scored(name, rec, amount=1_000_000, reasons=("porque no",)):
    """A scored offer with every key the renderer reads."""
    return {
        "offer_id": abs(hash(name)) % 10000,
        "name": name,
        "position": "DEL",
        "offer_amount": amount,
        "acq_price": 900_000,
        "acq_date": None,
        "acq_from": None,
        "roi": 100_000,
        "roi_pct": 11.0,
        "cf_price": 950_000,
        "vs_market": 50_000,
        "vs_market_pct": 5.0,
        "sf": 400,
        "tier_label": "⭐ Proyección media (SF 400)",
        "is_starter": False,
        "xi_loss": None,
        "breaks_xi": False,
        "replacement_name": None,
        "replacement_sf": None,
        "offerer": "🤖 Mercado público",
        "until": None,
        "recommendation": rec,
        "reasons": list(reasons),
    }


def test_a_rejected_offer_does_not_get_its_own_message():
    """Listing a squad returns one offer per player — fifteen notifications
    to say "no" fourteen times."""
    assert offers._is_muted(_scored("X", offers.REC_REJECT)) is True
    assert offers._is_muted(_scored("X", offers.REC_DOUBTFUL)) is False
    assert offers._is_muted(_scored("X", offers.REC_ACCEPT)) is False


def test_muting_can_be_turned_off_without_a_deploy():
    with patch.object(offers.config, "OFFERS_MUTE_REJECTED", False):
        assert offers._is_muted(_scored("X", offers.REC_REJECT)) is False


def test_the_muted_digest_still_names_every_offer_and_its_price():
    """Muted, never dropped: an offer worth taking against the advice has to
    stay visible, or the filter is hiding money."""
    text = offers._format_muted_digest(
        [
            _scored("Fulano", offers.REC_REJECT, 4_000_000, ["es tu titular"]),
            _scored("Mengano", offers.REC_REJECT, 9_000_000, ["pierdes 40%"]),
        ]
    )
    assert "Fulano" in text and "Mengano" in text
    assert "9.000.000" in text and "4.000.000" in text
    assert "es tu titular" in text and "pierdes 40%" in text
    # Highest offer first — the one most likely to be worth overriding.
    assert text.index("Mengano") < text.index("Fulano")
    assert "app de Biwenger" in text


def test_the_muted_digest_replaces_the_per_offer_messages():
    """Overriding a reasoned no should cost a trip to the app rather than a
    mistap in a notification — so the digest carries no buttons."""
    ctx = _ctx_with_offers([{"id": 1}, {"id": 2}])
    with patch(_p("require_telegram"), return_value=("tok", "chat")), patch(
        _p("_starter_ids"), return_value=set()
    ), patch(_p("_xi_baseline"), return_value=None), patch(
        _p("_score_offer"),
        side_effect=[
            _scored("A", offers.REC_REJECT),
            _scored("B", offers.REC_REJECT),
        ],
    ), patch(
        _p("send_telegram_message")
    ) as send:
        result = offers.run_offers_inbox(ctx)

    assert result["muted"] == 2 and result["actionable"] == 0
    assert send.call_count == 1  # one digest, not two offers
    assert "reply_markup" not in send.call_args.kwargs


def test_an_actionable_offer_still_arrives_with_its_buttons():
    ctx = _ctx_with_offers([{"id": 1}, {"id": 2}])
    with patch(_p("require_telegram"), return_value=("tok", "chat")), patch(
        _p("_starter_ids"), return_value=set()
    ), patch(_p("_xi_baseline"), return_value=None), patch(
        _p("_score_offer"),
        side_effect=[
            _scored("Vendible", offers.REC_ACCEPT),
            _scored("No", offers.REC_REJECT),
        ],
    ), patch(
        _p("send_telegram_message")
    ) as send:
        result = offers.run_offers_inbox(ctx)

    assert result == {"sent": 2, "offers": 2, "actionable": 1, "muted": 1}
    with_buttons = [c for c in send.call_args_list if "reply_markup" in c.kwargs]
    assert len(with_buttons) == 1
