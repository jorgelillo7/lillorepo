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
from packages.biwenger_tools.api.logic import custom_prediction as cp
from packages.biwenger_tools.api.logic import rows as rows_mod
from packages.biwenger_tools.api.logic.player_matching import build_jp_index

# --- tier_bid -------------------------------------------------------------
#
# Every tier carries a random 0-BID_JITTER_MAX € offset (anti-pattern), so
# expected bid values are checked as RANGES, not exact equalities. The few
# tests that need determinism patch `auto_bid._jitter` to a fixed return.


J = auto_bid.BID_JITTER_MAX


# Each tier bids a flat share over the price, set from the season's market:
# +5 % already wins ~75 % of auctions under 5M, and the contested stars go
# for +20-35 %. See the auto-bid spec for the table.


@pytest.mark.parametrize(
    "sf,price,expected,tier",
    [
        (910, 26_000_000, 36_400_000, "T1"),  # +40 %
        (620, 14_300_000, 17_160_000, "T2"),  # +20 % — Güler, won at 16.97M
        (500, 10_000_000, 11_000_000, "T3"),  # +10 %
        (350, 1_000_000, 1_050_000, "T4"),  # +5 %
    ],
)
def test_each_tier_bids_its_share_over_the_price(sf, price, expected, tier):
    bid, label = auto_bid.tier_bid(sf=sf, price=price, remaining_cash=100_000_000)
    assert expected <= bid <= expected + J
    assert tier in label


@pytest.mark.parametrize("sf", [910, 620])
def test_a_top_tier_short_of_cash_bids_the_whole_wallet(sf):
    """Güler: T2 wanted 17.16M against 16.38M of cash. Skipping him left the
    bot out of an auction it could have contested; T1 and T2 bid what there
    is instead — never more, so the wallet never goes negative."""
    cash = 16_376_085
    bid, label = auto_bid.tier_bid(sf=sf, price=14_300_000, remaining_cash=cash)
    assert cash - J <= bid <= cash
    assert "todo el saldo" in label


@pytest.mark.parametrize("sf", [500, 350])
def test_a_lower_tier_short_of_cash_is_left_to_the_caller(sf):
    """T3 and T4 are not worth emptying the wallet for: the bid comes back
    whole and the caller skips it for lack of cash."""
    bid, label = auto_bid.tier_bid(sf=sf, price=10_000_000, remaining_cash=1_000_000)
    assert bid > 1_000_000
    assert "todo el saldo" not in label


@pytest.mark.parametrize("sf", [910, 620])
def test_a_wallet_below_the_price_is_not_bid_as_a_whole(sf):
    """The market takes no bid under the asking price, so a wallet that does
    not reach it is skipped rather than offered whole."""
    bid, label = auto_bid.tier_bid(sf=sf, price=8_000_000, remaining_cash=3_000_000)
    assert bid > 3_000_000
    assert "todo el saldo" not in label


def test_a_top_tier_with_no_cash_is_left_to_the_caller():
    bid, _ = auto_bid.tier_bid(sf=850, price=10_000_000, remaining_cash=0)
    assert bid > 0


def test_tier_below_floor_returns_none():
    """SF < 300 → skip (T4 floor, inclusive)."""
    bid, reason = auto_bid.tier_bid(sf=299, price=1_000_000, remaining_cash=50_000_000)
    assert bid is None
    assert "300" in reason


@pytest.mark.parametrize(
    "sf,expected_band",
    [
        (701, "T1"),
        (700, "T1"),  # 700 inclusive — lands in T1, not T2
        (699, "T2"),
        (551, "T2"),
        (550, "T2"),  # 550 inclusive — T2, not T3
        (549, "T3"),
        (401, "T3"),
        (400, "T3"),  # 400 inclusive — T3, not T4 (user-requested boundary)
        (399, "T4"),
        (301, "T4"),
        (300, "T4"),  # 300 inclusive — T4, not skip
        (299, None),  # below T4 floor → skip
    ],
)
def test_tier_boundaries(sf, expected_band):
    """Pin the boundary semantics: thresholds are inclusive on the lower
    end (`>=`). A player at exactly TIER_X_MIN lands in that tier."""
    bid, label = auto_bid.tier_bid(sf=sf, price=1_000_000, remaining_cash=50_000_000)
    if expected_band is None:
        assert bid is None
    else:
        assert expected_band in label


def test_tier_jitter_is_within_advertised_range():
    """Sample the jitter empirically; it must never escape [0, BID_JITTER_MAX].
    SF 500 at 3M is T3: 3M × 1.10 = 3.3M nominal."""
    seen = set()
    for _ in range(500):
        bid, _ = auto_bid.tier_bid(sf=500, price=3_000_000, remaining_cash=50_000_000)
        seen.add(bid - 3_300_000)
    assert all(0 <= delta <= J for delta in seen)
    assert len(seen) > 10


def test_a_whole_wallet_bid_subtracts_the_jitter():
    """Capped at the wallet, the jitter comes off instead of on — a bid over
    the cash would be rejected by Biwenger."""
    cash = 30_000_000
    for _ in range(50):
        bid, _ = auto_bid.tier_bid(sf=910, price=26_000_000, remaining_cash=cash)
        assert cash - J <= bid <= cash


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


def test_build_candidates_keeps_valid_after_unmatched_player():
    """An unmatched player mid-list is skipped without aborting the scan: a
    valid candidate *after* it still makes the cut. Guards the `continue`
    against being weakened to a `break` (which would drop later actionable
    rows the moment one player is missing from the Biwenger map)."""
    market = [_sale(1), _sale(2)]  # id 1 absent from the map, id 2 present
    biwenger_players = {2: _bw(2, "Valid", 1_000_000)}
    jp = {"by_name": {"valid": _jp_with_sf("Valid", 500)}, "by_slug": {}}
    candidates = auto_bid._build_candidates(market, biwenger_players, jp)
    assert [c["player_id"] for c in candidates] == [2]


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
            "tier_label": "T2 precio+5M (SF 620)",
        },
    ]
    skipped = [
        {
            "name": "Bellingham",
            "kind": "no_cash",
            "sf": 650,
            "tier_label": "T2 (SF 650)",
            "bid": 14_000_000,
            "cash": 3_000_000,
        },
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


def test_format_telegram_text_no_cash_skip_shows_sf_and_tier():
    """The whole point of `kind=no_cash`: the user can tell what a richer
    wallet would have grabbed. Tier label + SF live in the skip line,
    and the icon is 💸 (not ⏭️) so it's visually distinct from a
    tier_low skip in the same message."""
    skipped = [
        {
            "name": "Bellingham",
            "kind": "no_cash",
            "sf": 650,
            "tier_label": "T2 (SF 650)",
            "bid": 14_000_000,
            "cash": 3_000_000,
        }
    ]
    text = auto_bid._format_telegram_text(
        day="2026-05-23",
        placed=[],
        skipped=skipped,
        total_bid=0,
        remaining_cash=3_000_000,
    )
    assert "💸 Sin pasta para <b>Bellingham</b>" in text
    assert "T2 (SF 650)" in text
    # `>` gets HTML-escaped to `&gt;` so Telegram's HTML parser doesn't
    # read it as a tag start (this is the 2026-05-24 regression).
    assert "puja 14.000.000 € &gt; cash 3.000.000 €" in text


def test_format_telegram_text_renders_each_skip_kind_with_own_icon():
    """Every kind branch renders a distinct icon. tier_low keeps the
    legacy ⏭️ + bare reason so a SF 280 skip still looks unchanged."""
    skipped = [
        {"name": "AlreadyBid", "kind": "already_bid"},
        {"name": "Reject", "kind": "biwenger_reject"},
        {"name": "LowTier", "kind": "tier_low", "sf": 280, "reason": "SF 280 < 300"},
    ]
    text = auto_bid._format_telegram_text(
        day="2026-05-23",
        placed=[],
        skipped=skipped,
        total_bid=0,
        remaining_cash=1_000_000,
    )
    assert "🔁 Ya pujado <b>AlreadyBid</b>" in text
    assert "⚠️ Biwenger rechazó <b>Reject</b>" in text
    assert "⏭️ Saltado <b>LowTier</b> (SF 280 &lt; 300)" in text


def test_format_telegram_text_html_escapes_user_content():
    """Regression for the 2026-05-24 silent fail: a skip reason like
    `"bid 1.000.000 € > cash 500.000 €"` contains a literal `>` which
    Telegram's HTML parser reads as a tag start → 400 Bad Request →
    the whole message is dropped. Every dynamic value must be escaped."""
    placed = [
        {
            # Name with `<` and `&` — the kind of edge case real-world
            # data can include.
            "name": "<Player & Co>",
            "bid": 1_000_000,
            "tier_label": "T3 precio+2M (SF 500)",
        }
    ]
    skipped = [
        {
            "name": "Bellingham",
            "kind": "no_cash",
            "sf": 650,
            # Tier label is rendered as-is; if it ever carries `<` or `&`
            # the escape must catch it.
            "tier_label": "T2 (SF 650)",
            "bid": 14_000_000,
            "cash": 3_000_000,
        }
    ]
    text = auto_bid._format_telegram_text(
        day="2026-05-24",
        placed=placed,
        skipped=skipped,
        total_bid=1_000_000,
        remaining_cash=3_000_000,
    )
    # Raw user-controlled `<`, `>`, `&` must NOT appear anywhere outside
    # of our intentional `<b>...</b>` wrappers.
    assert "&lt;Player &amp; Co&gt;" in text
    # `>` inside the no_cash line is the literal "bid > cash" separator.
    assert "puja 14.000.000 € &gt; cash 3.000.000 €" in text
    assert text.count("<b>") == text.count("</b>")  # balanced template tags
    assert "> cash" not in text  # no unescaped `>` left in the payload


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
        squad=None,
        oraculo_index=None,
    ):
        stack = ExitStack()
        mock_cfg = stack.enter_context(patch(_patches("config")))
        # `build_context()` returns the full orchestration context — patch
        # it once and feed a mock-Biwenger through. Beats patching the four
        # individual JP / Biwenger setup calls separately.
        biwenger = MagicMock()
        from packages.biwenger_tools.api.logic.orchestration import (
            OrchestratorContext,
        )
        from packages.biwenger_tools.api.logic.player_matching import build_jp_index

        ctx = OrchestratorContext(
            biwenger=biwenger,
            biwenger_players=biwenger_players,
            jp_index=build_jp_index(jp_players),
            oraculo_index=oraculo_index,
        )
        stack.enter_context(patch(_patches("build_context"), return_value=ctx))
        stack.enter_context(
            patch(
                _patches("_already_bid_ids"),
                return_value=set(already_bid_ids or []),
            )
        )
        stack.enter_context(patch(_patches("_log_bid")))
        # Pin jitter to 0 so the run-level assertions can stay on exact euros.
        # The jitter behaviour itself is covered by the tier_bid-level tests.
        stack.enter_context(patch(_patches("_jitter"), return_value=0))
        mock_send = stack.enter_context(
            patch(_patches("send_telegram_message_or_raise"))
        )

        mock_cfg.MARKET_URL = "x"
        mock_cfg.USER_SQUAD_URL = "x"
        mock_cfg.TELEGRAM_BOT_TOKEN = "tok" if telegram else ""
        mock_cfg.TELEGRAM_CHAT_ID = "chat" if telegram else ""

        biwenger.get_market_players.return_value = market_players
        # Default to an empty squad: the depth guard is exercised by its
        # own tests, and a MagicMock here would make every other test log
        # a swallowed TypeError from `build_squad_rows`.
        biwenger.get_manager_squad.return_value = squad or []
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
    """Realistic end-to-end: 3 candidates. The T1 bid (12M × 1.40 = 16.8M)
    leaves 3.2M, which covers neither Lewa's asking price nor Pedri's T3 bid
    (3.3M), so both are skipped for cash."""
    market = [_sale(1), _sale(2), _sale(3)]
    biwenger_players = {
        1: _bw(1, "Vinicius", 12_000_000),
        2: _bw(2, "Lewa", 8_000_000),
        3: _bw(3, "Pedri", 3_000_000),
    }
    jp_players = [
        _jp_with_sf("Vinicius", 910),
        _jp_with_sf("Lewa", 620),
        _jp_with_sf("Pedri", 500),
    ]
    biwenger, mock_send = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=20_000_000,
    )
    result = auto_bid.run_auto_bid()

    biwenger.place_market_bid.assert_called_once_with(player_id=1, amount=16_800_000)
    assert result["bid_count"] == 1
    assert result["total_bid_eur"] == 16_800_000
    assert result["remaining_cash_eur"] == 3_200_000
    assert result["skipped_count"] == 2  # Lewa + Pedri don't fit
    assert result["sent"] == 1
    mock_send.assert_called_once()


def test_run_auto_bid_first_too_expensive_does_not_block_cheaper_next(run_env):
    """Edge case the user asked about: 3 candidates by SF desc, the
    most expensive is unaffordable but the next one fits — the loop
    must keep going and bid the second one. Without the `continue` on
    `target_bid > remaining_cash`, the whole batch would be aborted.

    Setup:
    - cash = 5M.
    - P1 (SF 650, price 8M) → T2 bid 9.6M → no_cash skip (5M does not even
      cover the 8M asking price, so no whole-wallet bid either).
    - P2 (SF 620, price 2M) → T2 bid 2.4M → placed.
    - P3 (SF 280) → tier_low skip (below SF 300 floor, but >200 so it
      lands in the summary).
    """
    market = [_sale(1), _sale(2), _sale(3)]
    biwenger_players = {
        1: _bw(1, "Expensive", 8_000_000),
        2: _bw(2, "Cheaper", 2_000_000),
        3: _bw(3, "LowSf", 500_000),
    }
    jp_players = [
        _jp_with_sf("Expensive", 650),
        _jp_with_sf("Cheaper", 620),
        _jp_with_sf("LowSf", 280),
    ]
    biwenger, mock_send = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=5_000_000,
    )
    result = auto_bid.run_auto_bid()

    # Only the cheaper player gets a bid. The expensive one is skipped
    # by budget; the low-SF one is skipped by tier floor.
    biwenger.place_market_bid.assert_called_once_with(player_id=2, amount=2_400_000)
    assert result["bid_count"] == 1
    assert result["skipped_count"] == 2

    # Telegram message must visually distinguish the two skips: 💸 for
    # the budget skip (with SF + tier), ⏭️ for the irrelevant skip.
    text = mock_send.call_args.kwargs["text"]
    assert "💸 Sin pasta para <b>Expensive</b>" in text
    assert "T2 +20% (SF 650)" in text
    assert "⏭️ Saltado <b>LowSf</b>" in text


def test_run_auto_bid_sf_200_boundary_for_summary_line(run_env):
    """Boundary: a below-floor miss is surfaced in the summary only for
    SF > 200 (borderline-interesting), so SF exactly 200 is silently dropped
    to keep the message short while SF 201 shows up. Pins the `>` against a
    `>=` slip."""
    biwenger_players = {1: _bw(1, "Edge", 1_000_000)}
    for sf, expected_skips in ((200, 0), (201, 1)):
        biwenger, _ = run_env(
            market_players=[_sale(1)],
            biwenger_players=biwenger_players,
            jp_players=[_jp_with_sf("Edge", sf)],
            cash=30_000_000,
        )
        result = auto_bid.run_auto_bid()
        assert result["bid_count"] == 0
        assert result["skipped_count"] == expected_skips, f"SF {sf}"


def test_run_auto_bid_zero_account_cash_places_no_bid(run_env):
    """The account-state cash fallback (`get("cash") or 0`): a zero/falsy cash
    must resolve to 0, so even an all-in target is skipped for no_cash rather
    than bidding a stray euro off a `or 1`-style slip."""
    biwenger, _ = run_env(
        market_players=[_sale(1)],
        biwenger_players={1: _bw(1, "Star", 5_000_000)},
        jp_players=[_jp_with_sf("Star", 910)],
        cash=0,
    )
    result = auto_bid.run_auto_bid()

    biwenger.place_market_bid.assert_not_called()
    assert result["bid_count"] == 0
    assert result["skipped_count"] == 1  # no_cash


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
    gets its chance. Mirrors set_lineup's "log + continue" stance.

    Both candidates are SF 620 at price 1M → T2 bid = 1M × 1.20 = 1.2M."""
    market = [_sale(1), _sale(2)]
    biwenger_players = {
        1: _bw(1, "Vinicius", 1_000_000),
        2: _bw(2, "Lewa", 1_000_000),
    }
    jp_players = [
        _jp_with_sf("Vinicius", 620),  # T2 → bid 1.2M
        _jp_with_sf("Lewa", 620),  # T2 → bid 1.2M
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
    # Cash only decremented by the successful 1.2M bid (jitter pinned to 0
    # in run_env, so the math is exact here).
    assert result["remaining_cash_eur"] == 30_000_000 - 1_200_000


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


def test_run_auto_bid_raises_when_telegram_send_fails(run_env):
    """Regression for the silent fail: when Telegram refuses the summary
    (4xx parse error → `send_telegram_message_or_raise` raises
    TelegramDeliveryError), `run_auto_bid` must let it propagate so the
    route returns 500 and the bot can surface the failure to the user.
    Otherwise "⏳ procesando…" hangs forever and the user is blind."""
    from core.sdk.telegram import TelegramDeliveryError

    market = [_sale(1)]
    biwenger_players = {1: _bw(1, "Vinicius", 5_000_000)}
    jp_players = [_jp_with_sf("Vinicius", 910)]
    _, mock_send = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=30_000_000,
    )
    # Bids will have been placed by the time we hit the notify step —
    # the Firestore log keeps the audit trail.
    mock_send.side_effect = TelegramDeliveryError("delivery failed")

    with pytest.raises(TelegramDeliveryError):
        auto_bid.run_auto_bid()

    mock_send.assert_called_once()


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
    assert payload["name"] == "Vinicius"
    assert payload["bid"] == 30_000_000
    assert payload["offer_id"] == 99
    assert payload["status"] == "waiting"
    assert "created_at" in payload
    # Firestore TTL contract: expires_at must be exactly _LOG_TTL_DAYS in the
    # future, so the TTL policy on the `bids` collection-group gardens the
    # docs after the chosen retention window.
    from datetime import datetime, timedelta

    expires = payload["expires_at"]
    created = datetime.fromisoformat(payload["created_at"])
    assert expires - created == timedelta(days=auto_bid._LOG_TTL_DAYS)


# Quiet unused import warning when running just this file.
_ = MagicMock


# --- Suplentes: availability + squad depth guards -------------------------


def _jp_bench(name, sf):
    """A JP entry with a high score whom JP leaves out of its projected XI."""
    jp = _jp_with_sf(name, sf)
    jp["nextMatch"] = {"status": "pending", "playerInLineup": False}
    return jp


def _jp_injured(name, sf):
    jp = _jp_with_sf(name, sf)
    jp["status"] = "injured"
    return jp


def test_build_candidates_flags_bench_and_unavailable_players():
    """The two states JP scores highly and the tier ladder could not see."""
    market = [_sale(1), _sale(2), _sale(3)]
    biwenger_players = {
        1: _bw(1, "Titular", 5_000_000),
        2: _bw(2, "Banquillo", 5_000_000),
        3: _bw(3, "Lesionado", 5_000_000),
    }
    jp = {
        "by_name": {
            "titular": _jp_with_sf("Titular", 850),
            "banquillo": _jp_bench("Banquillo", 850),
            "lesionado": _jp_injured("Lesionado", 850),
        },
        "by_slug": {},
    }
    by_id = {
        c["player_id"]: c
        for c in auto_bid._build_candidates(market, biwenger_players, jp)
    }
    assert by_id[1]["uncalled"] is False and by_id[1]["unavailable"] is False
    assert by_id[2]["uncalled"] is True
    assert by_id[3]["unavailable"] is True


def test_bid_sf_caps_a_benched_star_out_of_the_all_in_tier():
    """The expensive half of the bug: `tier_bid` reads one number, and JP
    gives a benched star a T1 number. All-in means the whole wallet."""
    candidate = {"sf": 850, "uncalled": True}
    priced, reason = auto_bid.bid_sf(candidate, would_be_bench=False)
    assert priced < auto_bid.TIER_T2_MIN
    assert "suplente" in reason
    bid, label = auto_bid.tier_bid(priced, 5_000_000, 30_000_000, label_sf=850)
    assert "T3" in label and "850" in label  # priced as depth, reported honestly
    assert bid < 30_000_000


def test_bid_sf_caps_a_signing_who_would_sit_on_our_bench():
    candidate = {"sf": 850, "uncalled": False}
    priced, reason = auto_bid.bid_sf(candidate, would_be_bench=True)
    assert priced < auto_bid.TIER_T2_MIN
    assert "tu plantilla" in reason


def test_bid_sf_leaves_a_real_signing_alone():
    candidate = {"sf": 850, "uncalled": False}
    assert auto_bid.bid_sf(candidate, would_be_bench=False) == (850, None)


def test_bid_sf_does_not_annotate_a_player_already_below_the_cap():
    """Clamping a T3 to T3 changes no bid; saying so would put a
    bewildering note on a bid that never moved."""
    candidate = {"sf": 450, "uncalled": True}
    assert auto_bid.bid_sf(candidate, would_be_bench=True) == (450, None)


def test_would_be_bench_needs_every_position_covered():
    """A versatile player needs one door open, not all of them."""
    # DEF is stacked, MID is not.
    by_pos = {2: [700] * 6, 3: [100] * 6}
    versatile = {"sf": 400, "position_id": 2, "alt_positions": [3]}
    assert auto_bid._would_be_bench(versatile, by_pos) is False
    pure_def = {"sf": 400, "position_id": 2, "alt_positions": []}
    assert auto_bid._would_be_bench(pure_def, by_pos) is True


def test_would_be_bench_is_false_when_the_position_is_thin():
    by_pos = {1: [700]}  # one keeper owned, slots say 2
    assert auto_bid._would_be_bench({"sf": 10, "position_id": 1}, by_pos) is False


def test_would_be_bench_is_false_without_a_position():
    """A signal we do not have must not suppress a bid."""
    assert auto_bid._would_be_bench({"sf": 800, "position_id": None}, {}) is False


def test_run_auto_bid_skips_the_injured_and_does_not_all_in_the_benched(run_env):
    """End-to-end: the wallet survives a market of high-SF non-players."""
    market = [_sale(1), _sale(2)]
    biwenger_players = {
        1: _bw(1, "Lesionado", 5_000_000),
        2: _bw(2, "Banquillo", 5_000_000),
    }
    jp_players = [_jp_injured("Lesionado", 900), _jp_bench("Banquillo", 900)]
    biwenger, mock_send = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=30_000_000,
    )
    result = auto_bid.run_auto_bid()

    assert biwenger.place_market_bid.call_count == 1  # only the benched one
    bid = biwenger.place_market_bid.call_args.kwargs["amount"]
    assert bid == 5_500_000  # clamped to T3: 5M × 1.10
    assert result["remaining_cash_eur"] == 24_500_000
    text = mock_send.call_args.kwargs["text"]
    assert "🚑 No disponible" in text
    assert "rebajado" in text


# --- the market and the squad are measured with one ruler ------------------


def _oraculo_entry(name, slug, points):
    return {"playerName": name, "slug": slug, "predictedPoints": points, "chance": 90}


def _keeper(bw_id, name, price=1_000_000):
    return {"id": bw_id, "name": name, "position": 1, "price": price}


def test_the_market_and_the_squad_are_ranked_on_one_scale():
    """`_would_be_bench` compares a market candidate's projection against the
    squad's. Blending one side and not the other prices raw market numbers
    against blended squad ones, and every bid tilts the same way without
    anything in the output saying so.

    Raw JP ranks the candidate below both keepers already owned, so he is
    bench and no bid goes out. Oráculo rates him far above them; once both
    sides are blended he breaks into the depth chart.
    """
    entries = [
        _oraculo_entry("Newcomer", "newcomer-1", 9.0),
        _oraculo_entry("Owned A", "owned-a-2", 1.0),
        _oraculo_entry("Owned B", "owned-b-3", 0.9),
    ]
    oraculo_index = rows_mod.build_oraculo_index(entries)
    jp_index = build_jp_index(
        [
            {"name": n, "slug": s, "predict": [{"type": 2, "rate": r}]}
            for n, s, r in [
                ("Newcomer", "newcomer", 400),
                ("Owned A", "owned-a", 450),
                ("Owned B", "owned-b", 440),
            ]
        ]
    )
    biwenger_players = {
        1: _keeper(1, "Newcomer"),
        2: _keeper(2, "Owned A"),
        3: _keeper(3, "Owned B"),
    }
    scale = cp.build_scale(
        [
            {
                "oraculo_matched": True,
                "oraculo_points": pts,
                "jp_player": {"predict": [{"type": 2, "rate": rate}]},
            }
            for pts, rate in [(9.0, 500), (1.0, 300), (0.9, 290)]
        ]
    )

    squad = [{"id": 2}, {"id": 3}]
    market = [{"player": {"id": 1}}]

    raw_by_pos = auto_bid._squad_sf_by_position(
        rows_mod.build_squad_rows(squad, biwenger_players, jp_index)
    )
    raw = auto_bid._build_candidates(market, biwenger_players, jp_index)[0]
    assert auto_bid._would_be_bench(raw, raw_by_pos) is True

    blended_by_pos = auto_bid._squad_sf_by_position(
        rows_mod.build_squad_rows(
            squad,
            biwenger_players,
            jp_index,
            oraculo_index=oraculo_index,
            oraculo_scale=scale,
        )
    )
    blended = auto_bid._build_candidates(
        market,
        biwenger_players,
        jp_index,
        oraculo_index=oraculo_index,
        oraculo_scale=scale,
    )[0]
    assert blended["sf"] > raw["sf"]
    assert auto_bid._would_be_bench(blended, blended_by_pos) is False


def test_without_a_scale_every_projection_stays_raw_jp():
    """The Oráculo read fails often enough that this is the normal path, and
    it bids real money: no scale must mean byte-identical behaviour."""
    jp_index = build_jp_index(
        [{"name": "Solo", "slug": "solo", "predict": [{"type": 2, "rate": 420}]}]
    )
    biwenger_players = {1: _keeper(1, "Solo")}
    market = [{"player": {"id": 1}}]
    assert auto_bid._build_candidates(
        market, biwenger_players, jp_index, oraculo_index=None, oraculo_scale=None
    ) == auto_bid._build_candidates(market, biwenger_players, jp_index)
    assert (
        auto_bid._build_candidates(market, biwenger_players, jp_index)[0]["sf"] == 420
    )


# --- the chollos trade: buy cheap, let it rise, sell ------------------------


def _chollo_candidate(player_id, price, sf=100, chollo=True):
    return {
        "player_id": player_id,
        "name": f"Chollo {player_id}",
        "price": price,
        "sf": sf,
        "position_id": 3,
        "alt_positions": [],
        "unavailable": False,
        "uncalled": False,
        "chollo": chollo,
    }


def test_a_chollo_is_carried_off_the_shortlist_onto_the_candidate():
    entries = [
        {"playerName": "Ganga", "slug": "ganga-1", "predictedPoints": 2.0, "chance": 80}
    ]
    index = rows_mod.build_oraculo_index(entries, lists={"chollos": ["ganga-1"]})
    jp = build_jp_index(
        [{"name": "Ganga", "slug": "ganga", "predict": [{"type": 2, "rate": 100}]}]
    )
    candidates = auto_bid._build_candidates(
        [{"player": {"id": 1}}],
        {1: {"id": 1, "name": "Ganga", "position": 3, "price": 900_000}},
        jp,
        oraculo_index=index,
    )
    assert candidates[0]["chollo"] is True


def test_the_reserve_is_sized_on_the_day_s_own_chollos():
    """A fixed figure is wrong on both a quiet day and a busy one."""
    quiet = [_chollo_candidate(1, 500_000)]
    busy = [_chollo_candidate(i, 1_000_000) for i in range(1, 6)]
    assert (
        auto_bid._chollo_reserve(quiet, 50_000_000) == 500_000 + auto_bid.CHOLLO_MARGIN
    )
    # Never more than the day's bid allowance, however many are on offer.
    assert auto_bid._chollo_reserve(busy, 50_000_000) == auto_bid.CHOLLO_MAX_BIDS * (
        1_000_000 + auto_bid.CHOLLO_MARGIN
    )
    assert auto_bid._chollo_reserve([], 50_000_000) == 0


def test_the_reserve_never_exceeds_the_wallet():
    lots = [_chollo_candidate(i, 9_000_000) for i in range(1, 6)]
    assert auto_bid._chollo_reserve(lots, 1_000_000) == 1_000_000


def test_a_chollo_bid_is_the_asking_price_plus_a_thin_margin():
    """Weak on purpose: the market sells to the highest offer, so anyone who
    actually wants him outbids this. The ones that land are the ones nobody
    else bid on, which is the whole premise of the trade."""
    with patch.object(auto_bid, "_jitter", return_value=0):
        bid, label = auto_bid.chollo_bid(_chollo_candidate(1, 800_000))
    assert bid == 800_000 + auto_bid.CHOLLO_MARGIN
    assert "chollo" in label.lower()


def test_a_chollo_never_reaches_the_expensive_tiers():
    """The ladder is bypassed rather than loosened. `BENCH_PRICED_SF` exists
    because the ladder once went all-in on a benched star; a chollo is the
    same shape and a different bet, so it gets its own flat path instead of
    a clamp that would have to be weakened for everybody."""
    rich = _chollo_candidate(1, 20_000_000, sf=900)
    with patch.object(auto_bid, "_jitter", return_value=0):
        bid, _ = auto_bid.chollo_bid(rich)
    assert bid == 20_000_000 + auto_bid.CHOLLO_MARGIN


def _chollo_index(*names):
    return rows_mod.build_oraculo_index(
        [
            {
                "playerName": n,
                "slug": f"{n.lower()}-s",
                "predictedPoints": 2.0,
                "chance": 80,
            }
            for n in names
        ],
        lists={"chollos": [f"{n.lower()}-s" for n in names]},
    )


def test_a_chollo_is_bought_with_cash_the_ladder_left_reserved(run_env):
    """The ladder spends best-first, so "whatever is left" is usually nothing
    and the trade would only fire on days it was not needed. The reserve is
    held back before the ladder starts."""
    market = [_sale(1), _sale(2)]
    biwenger_players = {1: _bw(1, "Lewa", 2_000_000), 2: _bw(2, "Ganga", 800_000)}
    jp_players = [_jp_with_sf("Lewa", 620), _jp_with_sf("Ganga", 100)]
    biwenger, _ = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=5_000_000,
        oraculo_index=_chollo_index("Ganga"),
    )
    auto_bid.run_auto_bid()

    bids = {
        c.kwargs["player_id"]: c.kwargs["amount"]
        for c in biwenger.place_market_bid.call_args_list
    }
    assert bids[2] == 800_000 + auto_bid.CHOLLO_MARGIN
    assert 1 in bids  # the ladder still got its man


def test_a_top_tier_short_of_cash_takes_the_reserve_with_it(run_env):
    """One genuine star beats three lottery tickets: a T1 that wants more than
    the wallet (25M × 1.40 = 35M against 30M) bids all of it, reserve included,
    and the speculation stands down."""
    market = [_sale(1), _sale(2)]
    biwenger_players = {1: _bw(1, "Vini", 25_000_000), 2: _bw(2, "Ganga", 800_000)}
    jp_players = [_jp_with_sf("Vini", 910), _jp_with_sf("Ganga", 100)]
    biwenger, _ = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=30_000_000,
        oraculo_index=_chollo_index("Ganga"),
    )
    auto_bid.run_auto_bid()

    biwenger.place_market_bid.assert_called_once_with(player_id=1, amount=30_000_000)


def test_a_good_chollos_day_cannot_turn_the_wallet_into_bench_filler(run_env):
    """The daily ceiling. The owner cancels what does not convince in the
    app, so this is the safety net rather than the control."""
    names = ["G1", "G2", "G3", "G4", "G5"]
    market = [_sale(i) for i in range(1, 6)]
    biwenger_players = {i: _bw(i, n, 500_000) for i, n in enumerate(names, start=1)}
    jp_players = [_jp_with_sf(n, 100) for n in names]
    biwenger, _ = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=50_000_000,
        oraculo_index=_chollo_index(*names),
    )
    auto_bid.run_auto_bid()
    assert biwenger.place_market_bid.call_count == auto_bid.CHOLLO_MAX_BIDS


def test_the_reserve_yields_rather_than_block_a_real_signing(run_env):
    """Skipping a signing to keep three lottery tickets alive is the trade
    backwards. With room for only one of them, the ladder wins."""
    market = [_sale(1), _sale(2)]
    biwenger_players = {1: _bw(1, "Lewa", 2_000_000), 2: _bw(2, "Ganga", 800_000)}
    jp_players = [_jp_with_sf("Lewa", 620), _jp_with_sf("Ganga", 100)]
    biwenger, _ = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=2_800_000,
        oraculo_index=_chollo_index("Ganga"),
    )
    auto_bid.run_auto_bid()

    # The 2.4M T2 bid does not fit beside the 0.95M reserve; the reserve yields.
    biwenger.place_market_bid.assert_called_once_with(player_id=1, amount=2_400_000)


def test_the_trade_can_be_switched_off_without_a_deploy(run_env):
    """It spends money on players nobody intends to field, so the off switch
    must not require shipping code."""
    market = [_sale(1)]
    biwenger_players = {1: _bw(1, "Ganga", 800_000)}
    biwenger, _ = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=[_jp_with_sf("Ganga", 100)],
        cash=50_000_000,
        oraculo_index=_chollo_index("Ganga"),
    )
    with patch.object(auto_bid, "CHOLLO_MAX_BIDS", 0):
        auto_bid.run_auto_bid()
    biwenger.place_market_bid.assert_not_called()


def test_the_reserve_holds_against_a_bottom_tier_signing(run_env):
    """T4 is squad filler — SF 300-399, bid at 1.05x. A lottery ticket with an
    explicit exit is worth more than a marginal body, so the reserve that
    gives way to a real signing holds against this one."""
    market = [_sale(1), _sale(2)]
    biwenger_players = {1: _bw(1, "Relleno", 2_000_000), 2: _bw(2, "Ganga", 800_000)}
    jp_players = [_jp_with_sf("Relleno", 350), _jp_with_sf("Ganga", 100)]
    biwenger, _ = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=3_000_000,
        oraculo_index=_chollo_index("Ganga"),
    )
    auto_bid.run_auto_bid()

    # The T4 bid (2.1M) fits the wallet but not beside the reserve, and is not
    # worth breaking it for. The chollo is bought instead.
    biwenger.place_market_bid.assert_called_once_with(
        player_id=2, amount=800_000 + auto_bid.CHOLLO_MARGIN
    )


def test_the_reserve_still_yields_to_a_third_tier_signing(run_env):
    """The line is T3: at SF 400 and above the player is worth the wallet."""
    market = [_sale(1), _sale(2)]
    biwenger_players = {1: _bw(1, "Util", 2_000_000), 2: _bw(2, "Ganga", 800_000)}
    jp_players = [_jp_with_sf("Util", 450), _jp_with_sf("Ganga", 100)]
    biwenger, _ = run_env(
        market_players=market,
        biwenger_players=biwenger_players,
        jp_players=jp_players,
        cash=2_500_000,
        oraculo_index=_chollo_index("Ganga"),
    )
    auto_bid.run_auto_bid()

    # The 2.2M T3 bid (2M × 1.10) needs part of the reserve, and gets it.
    biwenger.place_market_bid.assert_called_once_with(player_id=1, amount=2_200_000)


def test_a_chollo_is_bid_on_before_oraculo_has_projected_anybody(run_env):
    """Monday through Wednesday the projections are nearly empty while the
    shortlists are already out. Requiring a projection meant the trade only
    ever fired on Thursday and Friday, losing most of the week's market."""
    index = rows_mod.build_oraculo_index(
        [],  # no projections yet
        lists={"chollos": ["ganga-7"]},
        shortlist_entries=[
            {"playerName": "Ganga", "slug": "ganga-7", "predictedPoints": 3.8}
        ],
    )
    biwenger, _ = run_env(
        market_players=[_sale(1)],
        biwenger_players={1: _bw(1, "Ganga", 800_000)},
        jp_players=[_jp_with_sf("Ganga", 100)],
        cash=10_000_000,
        oraculo_index=index,
    )
    auto_bid.run_auto_bid()
    biwenger.place_market_bid.assert_called_once_with(
        player_id=1, amount=800_000 + auto_bid.CHOLLO_MARGIN
    )
