"""Tests for the lineup optimizer."""

from packages.biwenger_tools.teams_analyzer.logic.lineup import (
    _is_available,
    _pick_captain,
    format_lineup_message,
    pick_lineup,
)

GK, DEF, MID, FWD = 1, 2, 3, 4


def _jp(sf=300, status="ok", match_status="pending"):
    predict = [{"type": 2, "rate": sf}] if sf else []
    return {
        "status": status,
        "predict": predict,
        "nextMatch": {"status": match_status, "playerInLineup": True},
    }


def _player(
    bw_id, pos, sf=300, status="ok", match_status="pending", price=5_000_000, alts=None
):
    return {
        "bw_id": bw_id,
        "name": f"Player{bw_id}",
        "position_id": pos,
        "alt_positions": alts or [],
        "price": price,
        "jp_player": _jp(sf, status, match_status),
    }


def _squad_444():
    """1 GK + 4 DEF + 4 MID + 4 FWD = 13 players, all available."""
    players = [_player(1, GK, sf=200)]
    for i in range(4):
        players.append(_player(10 + i, DEF, sf=300 + i * 10))
    for i in range(4):
        players.append(_player(20 + i, MID, sf=400 + i * 10))
    for i in range(4):
        players.append(_player(30 + i, FWD, sf=250 + i * 10))
    return players


# --- _is_available ---


def test_available_ok_player():
    assert _is_available(_player(1, GK)) is True


def test_unavailable_injured():
    assert _is_available(_player(1, GK, status="injured")) is False


def test_unavailable_suspended():
    assert _is_available(_player(1, GK, status="suspended")) is False


def test_unavailable_break():
    assert _is_available(_player(1, GK, match_status="break")) is False


def test_unavailable_no_jp():
    row = {
        "bw_id": 1,
        "name": "X",
        "position_id": GK,
        "alt_positions": [],
        "price": 0,
        "jp_player": None,
    }
    assert _is_available(row) is False


# --- pick_lineup ---


def test_pick_lineup_returns_11_starters():
    result = pick_lineup(_squad_444())
    assert result is not None
    assert len(result["starters"]) == 11


def test_pick_lineup_includes_one_gk():
    result = pick_lineup(_squad_444())
    gk_count = sum(1 for _, pos in result["starters"] if pos == GK)
    assert gk_count == 1


def test_pick_lineup_all_positions_filled():
    result = pick_lineup(_squad_444())
    for _, pos in result["starters"]:
        assert pos in (GK, DEF, MID, FWD)


def test_pick_lineup_no_duplicate_players():
    result = pick_lineup(_squad_444())
    ids = [r["bw_id"] for r, _ in result["starters"]]
    assert len(ids) == len(set(ids))


def test_pick_lineup_reserves_not_in_starters():
    result = pick_lineup(_squad_444())
    starter_ids = {r["bw_id"] for r, _ in result["starters"]}
    for r in result["reserves"]:
        assert r["bw_id"] not in starter_ids


def test_pick_lineup_reserves_at_most_4():
    result = pick_lineup(_squad_444())
    assert len(result["reserves"]) <= 4


def test_pick_lineup_excludes_injured():
    squad = _squad_444()
    # Add 2 extra MIDs so a 4-6-0 formation can be filled without FWDs
    squad.append(_player(40, MID, sf=350))
    squad.append(_player(41, MID, sf=360))
    # Injure all FWDs
    for r in squad:
        if r["position_id"] == FWD:
            r["jp_player"]["status"] = "injured"
    # Should still work with a formation that has 0 FWDs (4-6-0)
    result = pick_lineup(squad)
    assert result is not None
    fwd_count = sum(1 for _, pos in result["starters"] if pos == FWD)
    assert fwd_count == 0


def test_pick_lineup_returns_none_when_no_gk():
    squad = [_player(i, DEF, sf=300) for i in range(12)]
    assert pick_lineup(squad) is None


def test_pick_lineup_uses_alt_positions():
    # 1 GK, 4 DEF, 6 MID (one with FWD alt), 0 primary FWD
    # 4-5-1: place MID-as-FWD in FWD slot, 5 remaining MIDs fill MID, 4 DEFs fill DEF
    squad = [_player(1, GK)]
    for i in range(4):
        squad.append(_player(10 + i, DEF, sf=300))
    for i in range(6):
        squad.append(_player(20 + i, MID, sf=300))
    squad[5]["alt_positions"] = [FWD]  # squad[5] = player(20, MID) can also play FWD

    result = pick_lineup(squad)
    assert result is not None
    fwd_count = sum(1 for _, pos in result["starters"] if pos == FWD)
    assert fwd_count >= 1


# --- _pick_captain ---


def test_captain_prefers_cheap_player_with_high_sf():
    starters = [
        _player(1, GK, sf=500, price=10_000_000),  # expensive, high SF
        _player(2, DEF, sf=400, price=2_000_000),  # cheap, high SF
        _player(3, MID, sf=300, price=1_500_000),  # cheap, lower SF
    ]
    captain = _pick_captain(starters)
    assert captain["bw_id"] == 2  # cheap + highest SF among cheap


def test_captain_falls_back_to_highest_sf_when_no_cheap():
    starters = [
        _player(1, GK, sf=500, price=5_000_000),
        _player(2, DEF, sf=600, price=8_000_000),
    ]
    captain = _pick_captain(starters)
    assert captain["bw_id"] == 2


# --- format_lineup_message ---


def test_format_lineup_message_contains_formation():
    result = pick_lineup(_squad_444())
    msg = format_lineup_message(result)
    assert result["formation"] in msg


def test_format_lineup_message_marks_captain():
    result = pick_lineup(_squad_444())
    msg = format_lineup_message(result)
    assert " ©" in msg


def test_format_lineup_message_shows_sf_total():
    result = pick_lineup(_squad_444())
    msg = format_lineup_message(result)
    assert str(result["total_sf"]) in msg
