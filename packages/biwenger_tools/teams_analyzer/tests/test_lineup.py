"""Tests for the lineup optimizer."""

from packages.biwenger_tools.teams_analyzer.logic.lineup import (
    _is_available,
    _pick_captain,
    _try_fill,
    format_lineup_message,
    pick_lineup,
)

GK, DEF, MID, FWD = 1, 2, 3, 4


def _jp(sf=300, status="ok", match_status="pending", in_lineup=True):
    predict = [{"type": 2, "rate": sf}] if sf else []
    return {
        "status": status,
        "predict": predict,
        "nextMatch": {"status": match_status, "playerInLineup": in_lineup},
    }


def _player(
    bw_id,
    pos,
    sf=300,
    status="ok",
    match_status="pending",
    price=5_000_000,
    alts=None,
    in_lineup=True,
):
    return {
        "bw_id": bw_id,
        "name": f"Player{bw_id}",
        "position_id": pos,
        "alt_positions": alts or [],
        "price": price,
        "jp_player": _jp(sf, status, match_status, in_lineup=in_lineup),
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


def test_uncalled_player_is_available_with_penalty_sf():
    """JP says playerInLineup=False ("no convocado") — kept eligible but with
    SF penalised to 1 so the picker only uses them as a last resort.

    User-reported scenario 2026-05-17: the squad had a single GK and JP
    marked him uncalled. The previous "hard filter" rule made pick_lineup
    return None and Biwenger applied a -4 empty-slot penalty. We prefer
    fielding the uncalled player (0 points if he doesn't play) to losing
    the empty-slot penalty.
    """
    from packages.biwenger_tools.teams_analyzer.logic.lineup import (
        _UNCALLED_SF,
        _sf as lineup_sf,
    )

    p = _player(1, GK, sf=400, in_lineup=False)
    assert _is_available(p) is True
    assert lineup_sf(p) == _UNCALLED_SF


def test_uncalled_only_used_when_no_alternative():
    """In a single-slot duel, an uncalled SF=500 loses to a convocado SF=300.
    With only the uncalled player available, the picker still uses him."""
    convocado = _player(1, GK, sf=300, in_lineup=True)
    uncalled = _player(2, GK, sf=500, in_lineup=False)

    # Duel: convocado wins despite lower raw SF (uncalled gets penalised to 1).
    duel = pick_lineup(
        [
            convocado,
            uncalled,
            *[_player(10 + i, DEF, sf=300) for i in range(4)],
            *[_player(20 + i, MID, sf=300) for i in range(4)],
            *[_player(30 + i, FWD, sf=300) for i in range(2)],
        ]
    )
    assert duel is not None
    gk = next(r for r, pos in duel["starters"] if pos == GK)
    assert gk["bw_id"] == 1  # convocado picked

    # Same setup, only the uncalled GK available → still picked rather than
    # leaving an empty GK slot.
    only_uncalled = pick_lineup(
        [
            uncalled,
            *[_player(10 + i, DEF, sf=300) for i in range(4)],
            *[_player(20 + i, MID, sf=300) for i in range(4)],
            *[_player(30 + i, FWD, sf=300) for i in range(2)],
        ]
    )
    assert only_uncalled is not None
    gk = next(r for r, pos in only_uncalled["starters"] if pos == GK)
    assert gk["bw_id"] == 2  # uncalled picked as last resort


def test_available_when_lineup_unknown():
    """playerInLineup=None means JP doesn't know yet → still available."""
    p = _player(1, GK, sf=400)
    p["jp_player"]["nextMatch"]["playerInLineup"] = None
    assert _is_available(p) is True


def test_doubt_status_still_available():
    """Doubt is reported in the table but not filtered from the lineup —
    user wants to play those minutes (see commit thread 2026-05-17)."""
    p = _player(1, GK, sf=400, status="doubt")
    assert _is_available(p) is True


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
        if r is not None:
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


def test_pick_lineup_uses_alt_positions_when_needed():
    """When a formation cannot be filled with pure-position players, the
    algorithm uses alt_positions to bridge the gap.

    Setup (11 players total):
      - 1 GK
      - 4 pure DEFs
      - 4 pure MIDs
      - 1 multi MID/FWD
      - 1 pure FWD

    4-6-0 not viable (only 5 MIDs available). 4-5-1 wins: pure FWD at his
    slot, multi-MID/FWD stays at his MID primary (bias 0). 4-4-2 with the
    multi pushed to FWD would have bias -1 and lose the tiebreaker.
    """
    squad = [_player(1, GK)]
    for i in range(4):
        squad.append(_player(10 + i, DEF, sf=300))
    for i in range(4):
        squad.append(_player(20 + i, MID, sf=300))
    squad.append(_player(50, MID, sf=300, alts=[FWD]))  # multi MID/FWD
    squad.append(_player(60, FWD, sf=300))  # pure FWD

    result = pick_lineup(squad)
    assert result is not None
    by_id = {r["bw_id"]: pos for r, pos in result["starters"]}
    # Multi player stays at his primary MID (back-bias prefers it).
    assert by_id[50] == MID
    # Pure FWD fills the FWD slot.
    assert by_id[60] == FWD


def test_try_fill_picks_max_sf_for_single_slot():
    """For a single open DEF slot with two eligible candidates, the higher-SF
    one wins — even if it covers DEF only via alt_positions.
    Previously the function preferred the primary-position candidate (300)
    over the higher-SF alt candidate (350); the new exhaustive search picks
    the global optimum (SF 350)."""
    p_def = _player(1, DEF, sf=300)
    p_mid_alt_def = _player(2, MID, sf=350, alts=[DEF])
    slots = {DEF: 1}
    result = _try_fill([p_def, p_mid_alt_def], slots)
    assert result is not None
    assigned_player, _ = result[0]
    assert assigned_player["bw_id"] == 2  # SF 350 beats SF 300


def test_pick_lineup_breaks_sf_tie_by_back_position():
    """Reported by the user 2026-05-17 with a real /alinear output.

    Biwenger gives a per-position goal bonus (DEF +7, MID +5, DEL +4) that
    JP's SF does not model. When two formations tie on SF total, we prefer
    the one that puts more players further back than their primary, so the
    expected bonus from any goal they score is higher.

    Setup mirrors the lineup from the screenshot:
      - 1 GK
      - 3 pure DEFs (Huijsen 715, Affengruber 573, Bellerín 451)
      - 1 DEF/MID multi (Mingueza 447, primary DEF)
      - 1 DEF/MID multi (J.Iglesias 432, primary DEF)
      - 2 pure MIDs (Kubo 486, P.Martinez 434)
      - 1 DEL/MID multi (Tsygankov 495, primary DEL)
      - 2 pure FWDs (Mbappé 721, Jutglà 551)

    Multiple formations tie on SF total 5832. With the back-position
    tiebreaker 5-3-2 wins: both Mingueza and J.Iglesias stay at their
    primary DEF (so neither goes forward), and Tsygankov pulls back from
    his primary FWD to MED — net bias +1 (vs e.g. 4-4-2 where J.Iglesias
    would have to go forward to MED, giving bias 0).
    """
    squad = [
        _player(0, GK, sf=527),
        _player(1, DEF, sf=715),
        _player(2, DEF, sf=573),
        _player(3, DEF, sf=451),
        _player(10, DEF, sf=447, alts=[MID]),  # Mingueza
        _player(11, DEF, sf=432, alts=[MID]),  # J.Iglesias
        _player(12, MID, sf=486),  # Kubo
        _player(13, MID, sf=434),  # P.Martinez
        _player(20, FWD, sf=495, alts=[MID]),  # Tsygankov
        _player(21, FWD, sf=721),  # Mbappé
        _player(22, FWD, sf=551),  # Jutglà
    ]
    result = pick_lineup(squad)
    assert result is not None
    # Multiple valid formations sum to the same SF, so SF alone can't decide.
    assert result["total_sf"] == 5832
    assert result["formation"] == "5-3-2"
    by_id = {r["bw_id"]: pos for r, pos in result["starters"]}
    assert by_id[10] == DEF  # Mingueza at her primary
    assert by_id[11] == DEF  # J.Iglesias at her primary
    assert by_id[20] == MID  # Tsygankov pulled back from FWD primary


def test_try_fill_places_multiposition_where_it_maximises_total():
    """Real-world bug: a FWD/MID player must go to MID if doing so frees a
    better FWD trio. Setup mirrors the case reported by the user 2026-05-17:

      4 FWDs (one is multi-position FWD/MID with SF 400) and 3 MIDs.
      Formation has 3 MID + 3 FWD slots.

      Multi as FWD → FWDs 400+380+360=1140 · MIDs 350+320+280=950   → 2090
      Multi as MID → FWDs 380+360+340=1080 · MIDs 400+350+320=1070  → 2150  ← wins
    """
    multi = _player(1, FWD, sf=400, alts=[MID])  # FWD primary, MID alt
    fwd_b = _player(2, FWD, sf=380)
    fwd_c = _player(3, FWD, sf=360)
    fwd_d = _player(4, FWD, sf=340)
    mid_a = _player(10, MID, sf=350)
    mid_b = _player(11, MID, sf=320)
    mid_c = _player(12, MID, sf=280)

    slots = {MID: 3, FWD: 3}
    result = _try_fill([multi, fwd_b, fwd_c, fwd_d, mid_a, mid_b, mid_c], slots)
    assert result is not None

    multi_assignment = next(pos for r, pos in result if r["bw_id"] == 1)
    assert multi_assignment == MID  # placed at MID, not FWD primary

    total = sum(_sf(r) for r, _ in result)
    assert total == 2150


def _sf(row):
    """Helper mirroring lineup._sf for assertions."""
    jp = row["jp_player"]
    for entry in jp.get("predict") or []:
        if entry.get("type") == 2:
            return entry.get("rate", 0)
    return 0


# --- _pick_captain ---


def test_captain_prefers_cheap_player_with_high_sf():
    starters = [
        _player(1, GK, sf=500, price=10_000_000),  # expensive, high SF
        _player(2, DEF, sf=400, price=2_000_000),  # cheap, high SF
        _player(3, MID, sf=300, price=1_500_000),  # cheap, lower SF
    ]
    captain = _pick_captain(starters)
    assert captain["bw_id"] == 2  # cheap + highest SF among cheap


def test_captain_falls_back_to_cheapest_when_no_known_cheap():
    # No player has 0 < price < 3M — pick cheapest by price
    starters = [
        _player(1, GK, sf=500, price=5_000_000),
        _player(2, DEF, sf=600, price=8_000_000),
    ]
    captain = _pick_captain(starters)
    assert captain["bw_id"] == 1  # cheapest (5M < 8M), not best SF


def test_captain_excludes_zero_price_players():
    # price=0 means unknown MV — excluded even if best SF
    starters = [
        _player(1, GK, sf=600, price=0),  # unknown price, best SF
        _player(2, DEF, sf=300, price=2_000_000),  # cheap, known
    ]
    captain = _pick_captain(starters)
    assert captain["bw_id"] == 2


def test_captain_strict_below_3m():
    # Player with price exactly 3M is NOT eligible (rule: < 3M)
    starters = [
        _player(1, GK, sf=500, price=3_000_000),  # exactly 3M → not cheap
        _player(2, DEF, sf=300, price=2_999_999),  # just under → cheap
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
