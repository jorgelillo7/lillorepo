"""Tests for `logic/auto_bid.py` — tier table + multi-bid loop.

The tier rules are pinned to the user's spec exactly (memory
`project_market_autobid`). Touching the tier numbers should fail one
of these tests on purpose so a future change is forced to re-read the
contract.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from packages.biwenger_tools.api.logic import auto_bid

# --- tier_bid -------------------------------------------------------------


def test_tier_all_in_uses_remaining_cash_regardless_of_price():
    """SF > 800 must bid `remaining_cash`, NOT price+anything. A 26M player
    against 30M cash → 30M bid (the user's call: never leave cash on the
    table, never go negative on `maxBid`)."""
    bid, label = auto_bid.tier_bid(sf=910, price=26_000_000, remaining_cash=30_000_000)
    assert bid == 30_000_000
    assert "T1" in label and "all-in" in label


def test_tier_all_in_when_cash_is_zero_returns_zero_so_caller_skips():
    """remaining_cash=0 still returns 0 (not None); the caller's
    affordability check turns that into a skip with a "no cash" reason."""
    bid, _ = auto_bid.tier_bid(sf=850, price=10_000_000, remaining_cash=0)
    assert bid == 0


def test_tier_plus_5m_band():
    bid, label = auto_bid.tier_bid(sf=720, price=8_000_000, remaining_cash=50_000_000)
    assert bid == 13_000_000  # 8M + 5M
    assert "T2" in label


def test_tier_plus_2m_band():
    bid, label = auto_bid.tier_bid(sf=500, price=3_000_000, remaining_cash=50_000_000)
    assert bid == 5_000_000  # 3M + 2M
    assert "T3" in label


def test_tier_below_floor_returns_none():
    """SF ≤ 400 → skip (the user does not want low-rated noise)."""
    bid, reason = auto_bid.tier_bid(sf=400, price=1_000_000, remaining_cash=50_000_000)
    assert bid is None
    assert "400" in reason


@pytest.mark.parametrize(
    "sf,expected_band",
    [
        (801, "T1"),  # boundary just above all-in
        (800, "T2"),  # boundary: 800 is NOT all-in
        (601, "T2"),
        (600, "T3"),  # boundary: 600 falls to T3 band
        (401, "T3"),
        (400, None),  # boundary: 400 skipped
    ],
)
def test_tier_boundaries(sf, expected_band):
    """Pin the exact boundary semantics (strict `>` between bands)."""
    bid, label = auto_bid.tier_bid(sf=sf, price=1_000_000, remaining_cash=50_000_000)
    if expected_band is None:
        assert bid is None
    else:
        assert expected_band in label


# --- _build_candidates ----------------------------------------------------


def _bw(player_id, name, price):
    return {"id": player_id, "name": name, "price": price}


def _sale(player_id, user=None):
    sale = {"player": {"id": player_id}}
    if user is not None:
        sale["user"] = user
    return sale


def _jp_with_sf(name, sf):
    return {"name": name, "slug": name.lower(), "predict": [{"type": 2, "rate": sf}]}


def test_build_candidates_drops_user_listings_and_unmatched_players():
    market = [
        _sale(1),  # daily-market (computer-owned) → kept
        _sale(2, user={"id": 999}),  # user listing → dropped
        _sale(3),  # daily-market but no JP match → kept with sf=0
        _sale(4),  # daily-market but missing from biwenger_players → dropped
    ]
    biwenger_players = {
        1: _bw(1, "Vinicius", 10_000_000),
        3: _bw(3, "Unknown", 1_000_000),
    }
    jp_index = {
        "by_name": {"vinicius": _jp_with_sf("Vinicius", 900)},
        "by_slug": {"vinicius": _jp_with_sf("Vinicius", 900)},
    }
    candidates = auto_bid._build_candidates(market, biwenger_players, jp_index)
    ids = [c["player_id"] for c in candidates]
    assert ids == [1, 3]  # sorted SF desc (900, 0)
    assert candidates[0]["sf"] == 900
    assert candidates[1]["sf"] == 0


def test_build_candidates_sorts_by_sf_descending():
    market = [_sale(i) for i in (10, 20, 30)]
    biwenger_players = {i: _bw(i, f"P{i}", 1_000_000) for i in (10, 20, 30)}
    jp = {
        "by_name": {
            "p10": _jp_with_sf("P10", 500),
            "p20": _jp_with_sf("P20", 900),
            "p30": _jp_with_sf("P30", 700),
        },
        "by_slug": {},
    }
    candidates = auto_bid._build_candidates(market, biwenger_players, jp)
    assert [c["player_id"] for c in candidates] == [20, 30, 10]


# --- _format_telegram_text -----------------------------------------------


def test_format_telegram_text_renders_placed_skipped_and_totals():
    placed = [
        {"name": "Vinicius", "bid": 30_000_000, "tier_label": "T1 all-in (SF 910)"},
        {
            "name": "Lewandowski",
            "bid": 13_000_000,
            "tier_label": "T2 precio+5M (SF 720)",
        },
    ]
    skipped = [
        {"name": "Bellingham", "reason": "bid 14.000.000 € > cash 3.000.000 €"},
    ]
    text = auto_bid._format_telegram_text(
        day="2026-05-23",
        placed=placed,
        skipped=skipped,
        total_bid=43_000_000,
        remaining_cash=3_000_000,
    )
    assert "Vinicius" in text
    assert "30.000.000 €" in text
    assert "Lewandowski" in text
    assert "Bellingham" in text
    assert "Total pujado: <b>43.000.000 €</b>" in text
    assert "Cash restante: <b>3.000.000 €</b>" in text


def test_format_telegram_text_handles_no_candidates():
    text = auto_bid._format_telegram_text(
        day="2026-05-23",
        placed=[],
        skipped=[],
        total_bid=0,
        remaining_cash=10_000_000,
    )
    assert "Sin candidatos" in text
    assert "auto_bid_log/2026-05-23" in text


# --- run_auto_bid (end-to-end with mocks) --------------------------------


def _patches(target):
    return f"packages.biwenger_tools.api.logic.auto_bid.{target}"


@pytest.fixture
def run_env():
    """Pre-baked collaborator doubles for `run_auto_bid`.

    Use as: `run_env(market_players=..., biwenger_players=..., jp_players=...,
    cash=..., already_bid_ids=..., bid_side_effect=..., telegram=...)`. Yields
    `(biwenger_mock, send_mock)` after wiring every external dependency.
    """
    from contextlib import ExitStack

    def _enter(
        *,
        market_players,
        biwenger_players,
        jp_players,
        cash,
        already_bid_ids=None,
        bid_side_effect=None,
        telegram=True,
    ):
        stack = ExitStack()
        mock_cfg = stack.enter_context(patch(_patches("config")))
        stack.enter_context(patch(_patches("check_api_health")))
        stack.enter_context(
            patch(_patches("fetch_all_players"), return_value=jp_players)
        )
        mock_client_cls = stack.enter_context(patch(_patches("BiwengerClient")))
        stack.enter_context(
            patch(
                _patches("_already_bid_ids"),
                return_value=set(already_bid_ids or []),
            )
        )
        stack.enter_context(patch(_patches("_log_bid")))
        mock_send = stack.enter_context(patch(_patches("send_telegram_message")))

        mock_cfg.JP_AUTH_TOKEN = "tok"
        mock_cfg.JP_COMPETITION = 1
        mock_cfg.JP_SCORE_TYPE = 2
        mock_cfg.BIWENGER_EMAIL = "u"
        mock_cfg.BIWENGER_PASSWORD = "p"
        mock_cfg.LOGIN_URL = mock_cfg.ACCOUNT_URL = "x"
        mock_cfg.LEAGUE_ID = "1"
        mock_cfg.ALL_PLAYERS_DATA_URL = "x"
        mock_cfg.MARKET_URL = "x"
        mock_cfg.TELEGRAM_BOT_TOKEN = "tok" if telegram else ""
        mock_cfg.TELEGRAM_CHAT_ID = "chat" if telegram else ""

        biwenger = mock_client_cls.return_value
        biwenger.get_all_players_data_map.return_value = biwenger_players
        biwenger.get_market_players.return_value = market_players
        biwenger.get_account_state.return_value = {"cash": cash, "max_bid": cash}
        if bid_side_effect is not None:
            biwenger.place_market_bid.side_effect = bid_side_effect
        else:
            biwenger.place_market_bid.return_value = {
                "id": 999,
                "status": "waiting",
            }
        return biwenger, mock_send, stack

    with ExitStack() as outer:

        def factory(**kwargs):
            biwenger, mock_send, stack = _enter(**kwargs)
            # Defer cleanup to the outer stack so the test can call the factory
            # once and read the mocks without leaking patches.
            outer.callback(stack.close)
            return biwenger, mock_send

        yield factory


def test_run_auto_bid_places_tiered_bids_and_stops_when_cash_runs_out(run_env):
    """Realistic end-to-end: 3 candidates. SF 910 all-ins the cash, the
    next two get skipped because cash is now 0."""
    market = [_sale(1), _sale(2), _sale(3)]
    biwenger_players = {
        1: _bw(1, "Vinicius", 12_000_000),
        2: _bw(2, "Lewa", 8_000_000),
        3: _bw(3, "Pedri", 3_000_000),
    }
    jp_players = [
        _jp_with_sf("Vinicius", 910),
        _jp_with_sf("Lewa", 720),
        _jp_with_sf("Pedri", 500),
    ]
    biwenger, mock_send = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=30_000_000,
    )
    result = auto_bid.run_auto_bid()

    # 1 bid placed (Vinicius all-in 30M), Lewa+Pedri skipped (no cash left).
    biwenger.place_market_bid.assert_called_once_with(player_id=1, amount=30_000_000)
    assert result["bid_count"] == 1
    assert result["total_bid_eur"] == 30_000_000
    assert result["remaining_cash_eur"] == 0
    assert result["skipped_count"] == 2  # Lewa + Pedri don't fit
    assert result["sent"] == 1
    mock_send.assert_called_once()


def test_run_auto_bid_skips_already_bid_today(run_env):
    """Cloud Scheduler retry on 5xx: the player already in today's log is
    not re-bid even though they still match the tier rule."""
    market = [_sale(1)]
    biwenger_players = {1: _bw(1, "Vinicius", 5_000_000)}
    jp_players = [_jp_with_sf("Vinicius", 910)]
    biwenger, _ = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=30_000_000,
        already_bid_ids={1},
    )
    result = auto_bid.run_auto_bid()

    biwenger.place_market_bid.assert_not_called()
    assert result["bid_count"] == 0
    assert result["skipped_count"] == 1


def test_run_auto_bid_continues_when_biwenger_rejects_a_bid(run_env):
    """A 4xx on one bid must not abort the loop — the next candidate still
    gets its chance. Mirrors set_lineup's "log + continue" stance."""
    market = [_sale(1), _sale(2)]
    biwenger_players = {
        1: _bw(1, "Vinicius", 1_000_000),
        2: _bw(2, "Lewa", 1_000_000),
    }
    jp_players = [
        _jp_with_sf("Vinicius", 720),  # T2 → bid 6M
        _jp_with_sf("Lewa", 720),  # T2 → bid 6M
    ]
    err = requests.HTTPError("409 conflict")
    biwenger, _ = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=30_000_000,
        bid_side_effect=[err, {"id": 1, "status": "waiting"}],
    )
    result = auto_bid.run_auto_bid()

    assert biwenger.place_market_bid.call_count == 2
    assert result["bid_count"] == 1  # Vinicius rejected, Lewa accepted
    assert result["skipped_count"] == 1
    # Cash only decremented by the successful bid.
    assert result["remaining_cash_eur"] == 30_000_000 - 6_000_000


def test_run_auto_bid_skips_send_when_telegram_creds_missing(run_env):
    """No bot token → no Telegram call (still returns full summary)."""
    market = [_sale(1)]
    biwenger_players = {1: _bw(1, "Vinicius", 5_000_000)}
    jp_players = [_jp_with_sf("Vinicius", 910)]
    _, mock_send = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=30_000_000,
        telegram=False,
    )
    result = auto_bid.run_auto_bid()

    mock_send.assert_not_called()
    assert result["sent"] == 0
    assert result["bid_count"] == 1


# --- _log_bid + _already_bid_ids smoke -----------------------------------


def test_already_bid_ids_returns_empty_set_on_firestore_error():
    """Defensive: a Firestore outage must not stop the run silently. We
    return an empty dedup set (worst case: a rare double-bid on a retry)
    rather than skip every candidate."""
    with patch(
        _patches("firestore.list_documents"),
        side_effect=RuntimeError("firestore down"),
    ):
        assert auto_bid._already_bid_ids("2026-05-23") == set()


def test_log_bid_writes_expected_document():
    """`_log_bid` must persist the player id (as doc id) plus bid metadata
    so a retry can deduplicate against it."""
    candidate = {"player_id": 42, "name": "Vinicius", "sf": 910, "price": 12_000_000}
    offer = {"id": 99, "status": "waiting"}
    with patch.object(auto_bid.firestore, "set_document") as mock_set:
        auto_bid._log_bid("2026-05-23", candidate, 30_000_000, offer)
    assert mock_set.call_count == 1
    call_args = mock_set.call_args
    collection_path = call_args.args[0]
    doc_id = call_args.args[1]
    payload = call_args.args[2]
    assert collection_path == "auto_bid_log/2026-05-23/bids"
    assert doc_id == "42"
    assert payload["player_id"] == 42
    assert payload["bid"] == 30_000_000
    assert payload["offer_id"] == 99
    assert payload["status"] == "waiting"
    assert "created_at" in payload


# Quiet unused import warning when running just this file.
_ = MagicMock
