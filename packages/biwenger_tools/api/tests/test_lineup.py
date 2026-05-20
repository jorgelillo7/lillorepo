"""Tests for `_pick_captain`, `format_lineup_message`, and the cf-base
price kept by `build_squad_rows`.

`_pick_captain` gates on `row["price"]`, which is the cf.biwenger.com base
price — the same value Biwenger's server uses for its `Captain over max MV`
check. A row with `price=0` ("unknown") is excluded; the caller applies the
lineup without a captain when nobody qualifies.
"""

from packages.biwenger_tools.api.logic.lineup import (
    DEF,
    FWD,
    GK,
    MID,
    _CAPTAIN_MAX_PRICE,
    _pick_captain,
    format_lineup_message,
)
from packages.biwenger_tools.api.logic.rows import build_squad_rows


def _row(bw_id: int, price: int, sf: int) -> dict:
    """Minimal starter row: bw_id + price + a JP predict with SF type=2."""
    return {
        "bw_id": bw_id,
        "price": price,
        "jp_player": {"predict": [{"type": 2, "rate": sf}]},
    }


def test_pick_captain_picks_highest_sf_under_cap():
    starters = [
        _row(1, 1_000_000, sf=10),
        _row(2, 2_500_000, sf=80),  # highest SF under cap — picked
        _row(3, 2_900_000, sf=70),
        _row(4, 4_000_000, sf=200),  # over cap, excluded
    ]
    captain = _pick_captain(starters)
    assert captain is not None
    assert captain["bw_id"] == 2


def test_pick_captain_cap_is_strict():
    """A starter at exactly the cap is excluded (strict `<`)."""
    starters = [
        _row(1, _CAPTAIN_MAX_PRICE, sf=200),  # == cap, excluded
        _row(2, _CAPTAIN_MAX_PRICE - 1, sf=10),  # qualifies, picked
    ]
    captain = _pick_captain(starters)
    assert captain is not None
    assert captain["bw_id"] == 2


def test_pick_captain_returns_none_when_every_starter_over_cap():
    """No starter qualifies → None. The caller PUTs with captain=0."""
    starters = [
        _row(1, _CAPTAIN_MAX_PRICE, sf=100),
        _row(2, 5_000_000, sf=300),
    ]
    assert _pick_captain(starters) is None


def test_pick_captain_returns_none_when_all_prices_unknown():
    """Unknown price (0) is excluded — won't gamble a 403 on an unknown MV."""
    assert _pick_captain([_row(1, 0, sf=100), _row(2, 0, sf=200)]) is None


def test_pick_captain_ignores_unknown_price_when_known_options_exist():
    """A price-0 starter must not win even with the highest SF."""
    starters = [
        _row(1, 0, sf=500),  # unknown price, excluded
        _row(2, 1_500_000, sf=50),  # qualifies, picked
    ]
    captain = _pick_captain(starters)
    assert captain is not None
    assert captain["bw_id"] == 2


def _named(bw_id: int, name: str, price: int = 1_000_000, sf: int = 10) -> dict:
    row = _row(bw_id, price, sf)
    row["name"] = name
    return row


def test_format_lineup_message_renders_no_captain_warning():
    """With captain=None the rendered message must omit the © marker and
    add the manual-pick warning, but still announce the lineup as applied."""
    result = {
        "formation": "4-4-2",
        "starters": [(_named(1, "Keeper"), GK)] * 1
        + [(_named(2, "Defender"), DEF)] * 4
        + [(_named(3, "Midfielder"), MID)] * 4
        + [(_named(4, "Forward"), FWD)] * 2,
        "reserves": [None, None, None, None],
        "captain": None,
        "total_sf": 0,
    }
    msg = format_lineup_message(result)
    assert "Alineación aplicada" in msg
    assert "©" not in msg
    assert "Sin capitán" in msg
    assert "tope de 3M" in msg


# --- build_squad_rows: keeps cf-base price -------------------------------


def test_build_squad_rows_keeps_cf_base_price_ignoring_owner():
    """`row["price"]` must stay as the cf.biwenger.com base price — that is
    what Biwenger's server-side captain cap evaluates against.

    Regression for Pablo Martínez (player 4245, 2026-05-20): owner.price
    1.6M, cf-base 3.16M. We previously overrode `row["price"]` with
    owner.price, picked him as captain (eligible at 1.6M < 3M), and the
    server rejected with `Captain over max MV: 3160000 > 3000000`."""
    biwenger_players = {
        4245: {
            "id": 4245,
            "name": "Pablo Martínez",
            "position": 3,
            "altPositions": [],
            "price": 3_160_000,
        },
    }
    squad = [{"id": 4245, "owner": {"price": 1_600_000}}]
    rows = build_squad_rows(
        squad, biwenger_players, jp_index={"by_name": {}, "by_slug": {}}
    )
    assert len(rows) == 1
    assert rows[0]["price"] == 3_160_000


def test_build_squad_rows_keeps_cf_base_price_without_owner():
    """When the squad entry lacks an `owner` block, `row["price"]` is still
    the cf-base price."""
    biwenger_players = {
        7: {"id": 7, "name": "T", "position": 2, "altPositions": [], "price": 500_000},
    }
    rows = build_squad_rows(
        [{"id": 7}], biwenger_players, jp_index={"by_name": {}, "by_slug": {}}
    )
    assert rows[0]["price"] == 500_000
