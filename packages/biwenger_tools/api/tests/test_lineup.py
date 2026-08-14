"""Tests for `_pick_captain`, `format_lineup_message`, and the cf-base
price kept by `build_squad_rows`.

`_pick_captain` gates on `row["price"]`, which is the cf.biwenger.com base
price — the same value Biwenger's server uses for its `Captain over max MV`
check. A row with `price=0` ("unknown") is excluded; the caller applies the
lineup without a captain when nobody qualifies.
"""

import logging

from packages.biwenger_tools.api.logic.lineup import (
    DEF,
    FORMATIONS,
    FWD,
    GK,
    MID,
    CANNOT_PLAY,
    _CAPTAIN_MAX_PRICE,
    _POOL_PER_POSITION,
    _pick_captain,
    _pick_reserves,
    _sf,
    _trim_pool_by_position,
    format_lineup_message,
    pick_lineup,
)
from packages.biwenger_tools.api.logic import provider_watch
from packages.biwenger_tools.api.logic.rows import build_squad_rows
from packages.biwenger_tools.api.player_formatting import (
    availability,
    play_status_label,
)


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


def _player(
    bw_id,
    sf,
    position,
    alts=(),
    status="ok",
    called=True,
    fixture="pending",
    price=2_500_000,
):
    # Below `_CAPTAIN_MAX_PRICE`, not exactly on it. At 3M every player is
    # excluded from the captaincy, so a squad built from this helper used to
    # return `captain: None` and hide every regression in `_pick_captain`.
    return {
        "bw_id": bw_id,
        "name": f"P{bw_id}",
        "price": price,
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


# --- what the labels claim ------------------------------------------------


def test_a_projected_substitute_is_available_not_out():
    """JP's `playerInLineup` says he is outside their *projected eleven*, not
    that the club left him out. He comes on at the hour and scores, so calling
    him unavailable — and painting him the red of a torn quadriceps — claimed
    something the data never said."""
    bench = _player(1, 200, MID, called=False)["jp_player"]

    assert availability(bench) == "plays"
    assert play_status_label(bench) == "suplente"


def test_only_a_real_absence_counts_as_out():
    for jp in (
        _player(1, 5, MID, status="injured")["jp_player"],
        _player(2, 5, MID, status="sanctioned")["jp_player"],
        _player(3, 5, MID, fixture="break")["jp_player"],
    ):
        assert availability(jp) == "out"


def test_the_status_vocabulary_is_jps_own():
    """Measured against the live `fitness-daily` payload, 533 players.

    The code tested for "suspended" for months; JP never sends it. The word is
    `sanctioned`, so the branch was dead — hidden because JP also drops those
    players from its projected XI, where `playerInLineup` caught them one rung
    lower. Pinned so the next guess at this vocabulary has to be checked.
    """
    assert "sanctioned" in CANNOT_PLAY
    assert "injured" in CANNOT_PLAY
    assert "suspended" not in CANNOT_PLAY

    # `doubt` stays playable on purpose: JP prices the doubt into the rate
    # (the ten currently doubtful score 2-16 SF) rather than flagging them out.
    assert "doubt" not in CANNOT_PLAY
    assert availability(_player(4, 5, MID, status="doubt")["jp_player"]) == "plays"


def test_a_sanctioned_player_scores_below_an_uncalled_one():
    """The bug this vocabulary fix closes.

    A sanctioned player used to fall through to the `playerInLineup` rung and
    score 1 — level with someone merely left out of the projected XI. He cannot
    play at all, so he must rank below.
    """
    banned = _player(5, 5, MID, status="sanctioned")
    uncalled = _player(6, 5, MID, called=False)
    assert _sf(banned) < _sf(uncalled)


# --- The formation list must match Biwenger's own picker ---


def test_formations_match_biwengers_strategy_picker():
    """Transcribed from the app's "Estrategia" screen.

    Pinned because the list is data the code cannot derive: a formation
    missing here is an XI the optimizer will never propose, and nothing else
    would notice. Two were missing until this test existed.
    """
    biwenger_offers = {
        "3-4-3",
        "3-5-2",
        "4-3-3",
        "4-4-2",
        "4-5-1",
        "5-3-2",
        "5-4-1",
        "3-6-1",
        "3-3-4",
        "4-2-4",
        "4-6-0",
        "5-2-3",
        "3-2-5",
        "5-1-4",
    }
    assert {label for label, *_ in FORMATIONS} == biwenger_offers


def test_every_formation_fields_exactly_eleven():
    for label, n_def, n_mid, n_fwd in FORMATIONS:
        assert 1 + n_def + n_mid + n_fwd == 11, label
        # The search caps its candidate pool per position; a formation needing
        # more slots than the pool holds would silently lose the optimum.
        assert max(n_def, n_mid, n_fwd) <= _POOL_PER_POSITION, label


# --- Watching the providers for values this code does not model ---


def _watched(**jp):
    return {"name": "P", "jp_player": {"status": "ok", "nextMatch": {}, **jp}}


def test_an_unknown_jp_status_is_logged(caplog):
    with caplog.at_level(logging.WARNING):
        provider_watch.observe([_watched(status="loaned-out")])
    assert "never seen before" in caplog.text


def test_a_known_jp_status_is_silent(caplog):
    with caplog.at_level(logging.WARNING):
        for status in provider_watch.OBSERVED_JP_STATUS:
            provider_watch.observe([_watched(status=status)])
    assert caplog.text == ""


def test_the_first_break_fixture_is_logged(caplog):
    """`break` is handled by `_sf` and has never been observed in 533 players.
    Its first appearance answers a standing question about what it means."""
    with caplog.at_level(logging.WARNING):
        provider_watch.observe([_watched(nextMatch={"status": "break"})])
    assert "Fixture status never seen before" in caplog.text


def test_providers_disagreeing_on_availability_is_logged(caplog):
    """The Moussa Diarra case: JP says ok, Biwenger says injured. One in 481,
    and the one that gets an unavailable player fielded."""
    row = _watched(status="ok")
    row["bw_status"] = "injured"
    row["bw_status_info"] = "Lesión muscular."
    with caplog.at_level(logging.WARNING):
        provider_watch.observe([row])
    assert "disagree on availability" in caplog.text


def test_providers_agreeing_is_silent(caplog):
    with caplog.at_level(logging.WARNING):
        for jp, bw in (("ok", "ok"), ("injured", "injured"), ("doubt", "doubt")):
            row = _watched(status=jp)
            row["bw_status"] = bw
            provider_watch.observe([row])
    assert caplog.text == ""


def test_the_watcher_never_breaks_a_lineup(caplog):
    """An observer that can fail the thing it observes is worse than none."""
    with caplog.at_level(logging.WARNING):
        provider_watch.observe([{"jp_player": "not-a-dict"}])
    assert "lineup unaffected" in caplog.text


# --- A projected substitute worth starting ---


def test_a_strong_substitute_keeps_his_projection():
    """JP predicts the XI; it does not report it. Dani Olmo projected 659 and
    was left out of JP's eleven, so the old flat penalty scored him 1 — level
    with a 12-rated reserve keeper — and he was benched behind a 228 starter."""
    strong = _player(1, 659, MID, called=False)
    assert _sf(strong) == 659


def test_a_weak_substitute_still_ranks_below_everyone_playing():
    weak = _player(2, 81, MID, called=False)
    certain = _player(3, 228, MID)
    assert _sf(weak) == 1
    assert _sf(weak) < _sf(certain)


def test_the_threshold_is_tunable_without_a_deploy():
    import packages.biwenger_tools.api.config as api_cfg

    original = api_cfg.LINEUP_SUB_STARTS_ABOVE
    try:
        api_cfg.LINEUP_SUB_STARTS_ABOVE = 700
        assert _sf(_player(4, 659, MID, called=False)) == 1
        api_cfg.LINEUP_SUB_STARTS_ABOVE = 100
        assert _sf(_player(5, 659, MID, called=False)) == 659
    finally:
        api_cfg.LINEUP_SUB_STARTS_ABOVE = original


def test_an_unavailable_player_is_still_out_however_high_he_projects():
    """The threshold lifts a *substitute*, never someone who cannot play."""
    assert _sf(_player(6, 900, MID, status="injured")) == 0
    assert _sf(_player(7, 900, MID, status="sanctioned")) == 0
    assert _sf(_player(8, 900, MID, fixture="break")) == 0


def test_the_squad_that_prompted_this_now_starts_its_best_player():
    """The 2026-08-09 lineup: Olmo (659) benched and Danjuma (369) started,
    both scored 1, so the tie broke arbitrarily against the better player."""
    squad = [
        _player(1, 405, GK),
        _player(2, 523, DEF),
        _player(3, 433, DEF),
        _player(4, 415, DEF),
        _player(5, 409, DEF),
        _player(6, 228, DEF),
        _player(7, 538, MID),
        _player(8, 455, MID),
        _player(9, 428, MID),
        _player(10, 659, MID, called=False),  # Dani Olmo
        _player(11, 369, FWD, called=False),  # Danjuma
        _player(12, 416, FWD),
    ]
    result = pick_lineup(squad)
    starters = {r["bw_id"] for r, _ in result["starters"]}
    assert 10 in starters, "the 659 substitute must start"
    assert 11 in starters, "the 369 substitute clears the threshold too"


def test_a_promoted_substitute_never_gets_the_armband():
    """Starting him is a bet with the bench as insurance; captaining him
    doubles the bet and has none. Found by review after the threshold shipped:
    the flat penalty used to make this impossible, and the threshold quietly
    made it reachable for any cheap player with a high projection."""
    certain = _player(1, 380, MID, price=2_500_000)
    promoted = _player(2, 400, MID, called=False, price=2_900_000)
    captain = _pick_captain([certain, promoted])
    assert captain is not None
    assert captain["bw_id"] == 1, "the uncalled player must not be captain"


def test_no_captain_at_all_beats_an_uncalled_one():
    only_uncalled = [_player(3, 900, MID, called=False, price=2_000_000)]
    assert _pick_captain(only_uncalled) is None


def test_format_lineup_message_separates_promoted_from_hole_fillers():
    """One warning for both told the reader the opposite of the truth: a
    promoted 659 was reported as filling a hole while the starter he displaced
    sat on the bench two lines above."""
    promoted = _player(1, 659, MID, called=False)
    filler = _player(2, 10, MID, called=False)
    result = {
        "formation": "4-4-2",
        "starters": [(promoted, MID), (filler, MID)],
        "reserves": [],
        "captain": None,
        "total_sf": 660,
    }
    message = format_lineup_message(result)
    promo_block, _, filler_block = message.partition("⚠️ Aviso")
    assert "alineados por proyección" in promo_block
    assert "P1" in promo_block and "P1" not in filler_block
    assert "P2" in filler_block


# --- Capping promotions to one per position line ---


def test_only_the_top_promotion_in_a_line_keeps_his_projection():
    """Two promoted midfielders in the same line: Biwenger's auto-substitution
    insures at most one absent starter per line, so a second promotion there
    has no insurance if the bet is wrong. The lower one must fall back to
    `_UNCALLED_SF` and be outranked by a certain midfielder below the
    threshold."""
    squad = [
        _player(1, 405, GK),
        _player(2, 500, DEF),
        _player(3, 480, DEF),
        _player(4, 460, DEF),
        _player(5, 440, DEF),
        _player(6, 420, MID),
        _player(7, 400, MID),
        _player(8, 300, MID),  # certain, below threshold
        _player(9, 700, MID, called=False),  # top promotion, keeps projection
        _player(10, 600, MID, called=False),  # capped, falls to _UNCALLED_SF
        _player(11, 500, FWD),
        _player(12, 480, FWD),
    ]
    pick_lineup(squad)

    top = next(r for r in squad if r["bw_id"] == 9)
    second = next(r for r in squad if r["bw_id"] == 10)
    assert _sf(top) == 700
    assert _sf(second) == 1
    assert _sf(second) < _sf(next(r for r in squad if r["bw_id"] == 8))


def test_promotions_in_different_lines_are_both_kept():
    """The cap is per line, not global: a promoted MID and a promoted FWD
    must both keep their projection."""
    squad = [
        _player(1, 405, GK),
        _player(2, 500, DEF),
        _player(3, 480, DEF),
        _player(4, 460, DEF),
        _player(5, 440, DEF),
        _player(6, 420, MID),
        _player(7, 400, MID),
        _player(8, 380, MID),
        _player(9, 700, MID, called=False),
        _player(10, 360, FWD),
        _player(11, 650, FWD, called=False),
    ]
    pick_lineup(squad)

    promoted_mid = next(r for r in squad if r["bw_id"] == 9)
    promoted_fwd = next(r for r in squad if r["bw_id"] == 11)
    assert _sf(promoted_mid) == 700
    assert _sf(promoted_fwd) == 650


def test_a_capped_player_still_starts_when_his_line_has_no_certain_alternative():
    """The only two candidates for the MID line are both promoted. Capping
    the second to `_UNCALLED_SF` (1) still leaves him ahead of an empty
    slot, so the formation that needs two midfielders starts him anyway —
    the exact `4-2-4` squad (no DEF/FWD depth beyond the formation, no
    other MID at all) makes it the only feasible formation."""
    squad = [
        _player(1, 405, GK),
        _player(2, 500, DEF),
        _player(3, 480, DEF),
        _player(4, 460, DEF),
        _player(5, 440, DEF),
        _player(6, 700, MID, called=False),
        _player(7, 600, MID, called=False),
        _player(8, 500, FWD),
        _player(9, 480, FWD),
        _player(10, 460, FWD),
        _player(11, 440, FWD),
    ]
    result = pick_lineup(squad)

    assert result["formation"] == "4-2-4"
    starters = {r["bw_id"] for r, _ in result["starters"]}
    assert {6, 7} <= starters
    top = next(r for r in squad if r["bw_id"] == 6)
    capped = next(r for r in squad if r["bw_id"] == 7)
    assert top["_promotion_capped"] is False
    assert capped["_promotion_capped"] is True
    assert _sf(capped) == 1


def test_the_promotion_mark_is_not_stale_across_calls():
    """`pick_lineup` runs more than once per process on the same reused row
    dicts. Two promoted midfielders, called twice: if the mark were only
    ever set to `True` (never reset), the surviving promotion from the first
    call would stay capped on the second and both calls would disagree on
    who starts."""
    squad = [
        _player(1, 405, GK),
        _player(2, 500, DEF),
        _player(3, 480, DEF),
        _player(4, 460, DEF),
        _player(5, 440, DEF),
        _player(6, 420, MID),
        _player(7, 400, MID),
        _player(8, 300, MID),
        _player(9, 700, MID, called=False),
        _player(10, 600, MID, called=False),
        _player(11, 500, FWD),
        _player(12, 480, FWD),
    ]
    first = pick_lineup(squad)
    second = pick_lineup(squad)

    first_starters = {r["bw_id"] for r, _ in first["starters"]}
    second_starters = {r["bw_id"] for r, _ in second["starters"]}
    assert first_starters == second_starters
    top = next(r for r in squad if r["bw_id"] == 9)
    second_promo = next(r for r in squad if r["bw_id"] == 10)
    assert top["_promotion_capped"] is False
    assert second_promo["_promotion_capped"] is True


# --- Logging the bet: a promotion that starts, and its displaced starter ---

_PROMOTION_LOG_MESSAGE = "Uncalled substitute promoted into the lineup."


def _promo_records(caplog):
    return [r for r in caplog.records if r.getMessage() == _PROMOTION_LOG_MESSAGE]


def test_a_promotion_that_starts_is_logged_with_its_displaced_starter(caplog):
    """Five MID candidates for four MID slots: the certain player with the
    lowest SF is the one who ends up on the bench, and that is who the
    promotion must name as displaced — the counterfactual a later audit
    grades against the round's real points."""
    squad = [
        _player(1, 405, GK),
        _player(2, 500, DEF),
        _player(3, 480, DEF),
        _player(4, 460, DEF),
        _player(5, 440, DEF),
        _player(6, 420, MID),
        _player(7, 400, MID),
        _player(8, 350, MID),
        _player(9, 228, MID),  # certain, lowest SF — displaced from the XI
        _player(10, 700, MID, called=False),
        _player(11, 500, FWD),
        _player(12, 480, FWD),
    ]
    with caplog.at_level(logging.WARNING):
        result = pick_lineup(squad)

    assert result["formation"] == "4-4-2"
    starters = {r["bw_id"] for r, _ in result["starters"]}
    assert 9 not in starters
    promo_records = _promo_records(caplog)
    assert len(promo_records) == 1
    record = promo_records[0]
    assert record.player == "P10"
    assert record.projection == 700
    assert record.position == "MED"
    assert record.displaced_player == "P9"
    assert record.displaced_sf == 228


def test_a_promotion_with_no_certain_alternative_is_logged_with_displaced_none(caplog):
    squad = [
        _player(1, 405, GK),
        _player(2, 500, DEF),
        _player(3, 480, DEF),
        _player(4, 460, DEF),
        _player(5, 440, DEF),
        _player(6, 420, MID),
        _player(7, 400, MID),
        _player(8, 380, MID),
        _player(9, 700, MID, called=False),
        _player(10, 360, FWD),
        _player(11, 340, FWD),
    ]
    with caplog.at_level(logging.WARNING):
        pick_lineup(squad)

    promo_records = _promo_records(caplog)
    assert len(promo_records) == 1
    assert promo_records[0].displaced_player is None
    assert promo_records[0].displaced_sf is None


def test_a_promotion_that_does_not_start_is_not_logged(caplog):
    """The second promotion in a capped line loses out and never reaches the
    XI at full projection — no bet was placed, so nothing is logged for it."""
    squad = [
        _player(1, 405, GK),
        _player(2, 500, DEF),
        _player(3, 480, DEF),
        _player(4, 460, DEF),
        _player(5, 440, DEF),
        _player(6, 420, MID),
        _player(7, 400, MID),
        _player(8, 300, MID),
        _player(9, 700, MID, called=False),
        _player(10, 600, MID, called=False),
        _player(11, 500, FWD),
        _player(12, 480, FWD),
    ]
    with caplog.at_level(logging.WARNING):
        pick_lineup(squad)

    logged_names = {r.player for r in _promo_records(caplog)}
    assert "P9" in logged_names
    assert "P10" not in logged_names


def test_log_promotions_never_raises(caplog):
    """Mirrors `test_the_watcher_never_breaks_a_lineup`: malformed promotion
    entries must not propagate into the lineup path."""
    with caplog.at_level(logging.WARNING):
        provider_watch.log_promotions(["not-a-dict"])
    assert "lineup unaffected" in caplog.text


def test_a_promoted_substitute_is_not_painted_red():
    """Three surfaces were telling three stories about the same player: the
    lineup started Olmo at 659, the message explained why, and the squad image
    marked him red for not being in JP's XI."""
    from packages.biwenger_tools.api.player_formatting import status_emoji

    promoted = _player(1, 659, MID, called=False)["jp_player"]
    weak_sub = _player(2, 81, MID, called=False)["jp_player"]
    assert status_emoji(promoted) == "🟢"
    assert status_emoji(weak_sub) == "🔴"


def test_the_cap_holds_for_the_line_a_player_is_actually_assigned_to():
    """A multi-position promotion must not smuggle a second bet into a line.

    The cap groups by primary position, but the optimizer assigns by any
    position a player covers. P9 is a promoted defender who plays midfield:
    five stronger certain defenders keep him out of his own line, so he lands
    in midfield next to P10, the promotion the cap already allowed there.
    Two bets, one midfield bench slot — the exact exposure the cap exists to
    prevent.
    """
    squad = [
        _player(1, 405, GK),
        _player(2, 520, DEF),
        _player(3, 515, DEF),
        _player(4, 510, DEF),
        _player(5, 505, DEF),
        _player(6, 502, DEF),
        _player(7, 200, MID),
        _player(8, 190, MID),
        _player(12, 180, MID),
        _player(9, 500, DEF, alts=(MID,), called=False),
        _player(10, 450, MID, called=False),
        _player(11, 300, FWD),
        _player(13, 290, FWD),
    ]
    result = pick_lineup(squad)
    assert result is not None

    promoted_per_line: dict[int, int] = {}
    for row, pos_id in result["starters"]:
        if row["jp_player"]["nextMatch"]["playerInLineup"] is False and _sf(row) > 1:
            promoted_per_line[pos_id] = promoted_per_line.get(pos_id, 0) + 1

    assert not [
        line for line, n in promoted_per_line.items() if n > 1
    ], f"a line started more than one promoted substitute: {promoted_per_line}"


def test_a_player_jornada_perfecta_does_not_carry_is_logged(caplog):
    """The observer skipped the one case it was best placed to catch. A
    player JP has no entry for scores zero, so his owner fields someone the
    optimizer cannot see — and when that took the league ranking down,
    nothing in the logs could name him."""
    rows = [{"name": "Ter Stegen", "bw_id": 99, "jp_player": None}]
    with caplog.at_level(logging.WARNING):
        provider_watch.observe(rows)

    assert "No Jornada Perfecta entry" in caplog.text
    assert "Ter Stegen" in str(caplog.records[0].player)


def test_a_matched_player_is_not_reported_as_missing(caplog):
    """The gap is a couple of dozen names league-wide; a squad of matched
    players must stay silent or the signal drowns."""
    rows = [
        {
            "name": "Canales",
            "bw_id": 1,
            "jp_player": {
                "status": "ok",
                "nextMatch": {"status": "pending", "playerInLineup": True},
                "predict": [{"type": 2, "rate": 538}],
            },
        }
    ]
    with caplog.at_level(logging.WARNING):
        provider_watch.observe(rows)

    assert "No Jornada Perfecta entry" not in caplog.text


def test_playing_a_forward_in_midfield_is_worth_one_bonus_point():
    """Biwenger pays more for a goal the further back it is scored: DEL 4,
    MED 5. A DEL/MED covering midfield gains that difference."""
    from packages.biwenger_tools.api.logic.lineup import _back_bias_one

    assert _back_bias_one(_player(1, 400, FWD, (MID,)), MID) == 1


def test_pushing_a_defender_into_midfield_costs_two():
    """DEF 7 → MED 5. This is why moving one player back to make room by
    moving another forward is usually a loss, not a wash."""
    from packages.biwenger_tools.api.logic.lineup import _back_bias_one

    assert _back_bias_one(_player(1, 400, DEF, (MID,)), MID) == -2


def test_a_player_in_his_own_position_is_worth_nothing_either_way():
    """The measure is displacement, not formation. Summing the slots' own
    bonuses would always prefer five defenders even with nobody moved."""
    from packages.biwenger_tools.api.logic.lineup import _back_bias_one

    for pos in (GK, DEF, MID, FWD):
        assert _back_bias_one(_player(1, 400, pos), pos) == 0


def test_the_two_candidate_elevens_no_longer_tie():
    """The squad that raised this: 5-4-1 and 4-6-0 projected the same 4326,
    and under a direction-only bias both scored +1 — so the winner was
    whichever came first in `FORMATIONS`, a list transcribed from the app in
    no meaningful order.

    Asserted on the bias itself rather than on the formation `pick_lineup`
    returns: the old code also returned 5-4-1, by accident of list position,
    so asserting the formation proves nothing about why.

    Fielding Iván Romero in midfield gains 1 (DEL 4 → MED 5), but frees the
    slot only by pushing Bretones out of defence, which costs 2 (DEF 7 → MED
    5). The eleven that leaves both where they belong is worth more.
    """
    from packages.biwenger_tools.api.logic.lineup import _back_bias

    romero = _player(10, 416, FWD, (MID,))
    bretones = _player(6, 303, DEF, (MID,))
    danjuma = _player(11, 197, FWD, (MID,), called=False)
    keeper = _player(1, 405, GK)

    as_5_4_1 = [(keeper, GK), (bretones, DEF), (romero, FWD), (danjuma, MID)]
    as_4_6_0 = [(keeper, GK), (bretones, MID), (romero, MID), (danjuma, MID)]

    assert _back_bias(as_5_4_1) == 1
    assert _back_bias(as_4_6_0) == 0
    assert _back_bias(as_5_4_1) > _back_bias(as_4_6_0)


def test_between_two_fallbacks_the_better_projection_starts():
    """`_sf` floors every uncalled player below the threshold to the same
    value, which threw away that one projects 316 and the other 197. If a
    slot must go to someone JP does not expect on the pitch, it goes to the
    one most likely to be worth something."""
    squad = [
        _player(1, 405, GK),
        _player(2, 523, DEF),
        _player(3, 433, DEF),
        _player(4, 415, DEF),
        _player(5, 409, DEF),
        _player(6, 538, MID),
        _player(7, 455, MID),
        _player(9, 428, MID),
        _player(10, 416, FWD),
        _player(11, 380, FWD),
        # the fourth midfield slot has only these two, and both are floored
        _player(12, 316, MID, (FWD,), called=False),  # the better gamble
        _player(13, 197, FWD, (MID,), called=False),  # gains +1 dropping back
    ]
    result = pick_lineup(squad)
    assert result is not None
    names = [r["name"] for r, _ in result["starters"]]
    assert "P12" in names
    assert "P13" not in names


def test_the_projection_gap_outranks_the_bonus_it_could_gain():
    """The two are orders of magnitude apart: the bias is worth a point or
    two of goal bonus, the gap between fallbacks is hundreds of projected
    points. Ranked the other way round — as it was — a 197 who gains +1 by
    dropping back beat a 316 who gains nothing, and an 11.2M substitute sat
    on the bench behind him."""
    better = _player(7, 316, MID, (FWD,), called=False)  # MID at MID: bias 0
    worse = _player(8, 197, FWD, (MID,), called=False)  # FWD at MID: bias +1

    from packages.biwenger_tools.api.logic.lineup import _back_bias_one, _fallback_rate

    assert _back_bias_one(worse, MID) > _back_bias_one(better, MID)
    assert _fallback_rate(better) > _fallback_rate(worse)


def test_an_injured_player_is_never_the_better_gamble():
    """An injured 400 is not a better bet than an uncalled 200 — he is not
    expected on the pitch at all, and ranking him first would field him."""
    from packages.biwenger_tools.api.logic.lineup import _fallback_rate

    injured = _player(1, 400, MID, status="injured")
    uncalled = _player(2, 200, MID, called=False)
    assert _fallback_rate(injured) == 0
    assert _fallback_rate(uncalled) == 200


def test_the_bench_prefers_the_substitute_most_likely_to_be_worth_something():
    """A doubtful forward projecting 63 and a fit one projecting 197 both
    floor to `_UNCALLED_SF`, and the bench was choosing between them by squad
    order — it picked the doubtful one on a real squad. The bench exists for
    the day a starter does not play, so the slot goes to whoever has
    something behind him.

    Asserted on the slot, not on membership: with two bench places free both
    players are benched either way, and only the order tells them apart.
    """
    squad = [
        _player(1, 405, GK),
        _player(2, 523, DEF),
        _player(3, 433, DEF),
        _player(4, 415, DEF),
        _player(5, 409, DEF),
        _player(6, 538, MID),
        _player(7, 455, MID),
        _player(8, 428, MID),
        _player(9, 300, MID),
        _player(10, 416, FWD),
        _player(11, 380, FWD),
        _player(12, 183, MID),  # takes the midfield bench slot on merit
        _player(13, 63, FWD, (MID,), status="doubt", called=False),  # Rioja
        _player(14, 197, FWD, (MID,), called=False),  # Danjuma
    ]
    result = pick_lineup(squad)
    assert result is not None

    _gk, _df, mid_sub, fwd_sub = result["reserves"]
    assert mid_sub is not None and mid_sub["name"] == "P12"
    assert fwd_sub is not None and fwd_sub["name"] == "P14"


def test_a_versatile_substitute_covers_more_than_a_narrow_one():
    """Biwenger's auto-substitution replaces a starter with a bench player
    who covers that position, so a DEL/MED reaches two lines where a
    MED-only reaches one. It is the last thing consulted, after the score
    and the projection."""
    from packages.biwenger_tools.api.logic.lineup import _bench_rank

    versatile = _player(1, 200, FWD, (MID,), called=False)
    narrow = _player(2, 200, FWD, called=False)
    assert _bench_rank(versatile) > _bench_rank(narrow)


def test_the_bench_never_outranks_a_player_who_is_actually_playing():
    """Projection breaks ties among the floored; it must not lift one above
    a substitute JP expects on the pitch."""
    from packages.biwenger_tools.api.logic.lineup import _bench_rank

    playing = _player(1, 183, MID)
    floored = _player(2, 197, MID, called=False)
    assert _bench_rank(playing) > _bench_rank(floored)
