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
    _pick_reserves,
    _sf,
    _trim_pool_by_position,
    format_lineup_message,
    pick_lineup,
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


# --- filling every slot: an empty one scores -4, a player who does not play 0 --


def _player(bw_id, sf, position, alts=(), status="ok", called=True, fixture="pending"):
    return {
        "bw_id": bw_id,
        "name": f"P{bw_id}",
        "price": 3_000_000,
        "position_id": position,
        "alt_positions": list(alts),
        "jp_player": {
            "status": status,
            "nextMatch": {"status": fixture, "playerInLineup": called},
            "predict": [{"type": 2, "rate": sf}],
        },
    }


def _exactly_eleven():
    """A squad that fills 4-4-2 with nothing left over, so every bench slot is
    empty until something is added. Any bench name is therefore the addition."""
    return (
        [_player(1, 400, GK)]
        + [_player(10 + i, 300 - i, DEF) for i in range(4)]
        + [_player(20 + i, 200 - i, MID) for i in range(4)]
        + [_player(30 + i, 100 - i, FWD) for i in range(2)]
    )


def _bench_names(result):
    return [r["name"] if r else None for r in result["reserves"]]


def test_a_bare_eleven_leaves_every_bench_slot_empty():
    """The baseline the next two tests measure against."""
    assert _bench_names(pick_lineup(_exactly_eleven())) == [None] * 4


def test_an_injured_player_fills_a_bench_slot_rather_than_leaving_it_empty():
    """The regression that shipped: injured and suspended players were dropped
    before the bench was picked, so slots stayed open. An open slot costs -4; a
    player who does not play costs 0, and fixtures do get postponed."""
    squad = _exactly_eleven() + [_player(90, 5, FWD, status="injured")]

    assert "P90" in _bench_names(pick_lineup(squad))


def test_a_player_with_no_fixture_still_fills_a_slot():
    squad = _exactly_eleven() + [_player(91, 5, DEF, fixture="break")]

    assert "P91" in _bench_names(pick_lineup(squad))


def test_a_healthy_player_always_outranks_a_doubtful_one():
    """The fallbacks must never displace somebody who is going to play."""
    squad = _exactly_eleven() + [
        _player(92, 300, FWD, status="injured"),
        _player(93, 250, FWD),
    ]
    result = pick_lineup(squad)

    starters = {row["name"] for row, _ in result["starters"]}
    assert "P93" in starters
    assert "P92" not in starters


def test_the_bench_is_drawn_from_the_whole_squad_not_the_trimmed_pool():
    """`_trim_pool_by_position` keeps the top 8 per position to bound the
    starter search. It used to feed the bench too, so a midfielder ranked ninth
    among midfield-eligible players vanished before the bench was considered —
    which is how a fifteen-man squad fielded a bench of one.

    Asserted against the trimmed pool directly: the formation search would
    otherwise decide which players are spare, and that is not what is on
    trial here.
    """
    crowded = [_player(40 + i, 320 - i, DEF, alts=[MID]) for i in range(9)]
    ninth = _player(99, 3, MID)
    squad = crowded + [ninth]

    trimmed = _trim_pool_by_position(sorted(squad, key=_sf, reverse=True))
    assert ninth not in trimmed  # the pool the starter search sees drops him

    reserves = _pick_reserves(squad, starter_ids={p["bw_id"] for p in crowded})
    assert reserves[2] is ninth  # …and the bench finds him anyway
