"""Tests for the draft skill's analysis scripts.

These scripts produce the decisions, and they were unprotected: the availability
metric shipped inverted, was written up in the SKILL as a success, and was only
caught mid-draft when a player it had declared unreachable turned out to be
sitting on the board. What is covered here is what fails *silently* — a wrong
number that still looks like a number.

Nothing here touches the network or Firestore.
"""

import os
import sys

import pytest

# Under Bazel, import the runfiles copy — the one coverage measures and
# reports; with plain pytest, the source tree. `.claude` cannot be a package
# name, so these scripts cannot be imported by module path.
_SCRIPTS = (
    os.path.join(
        os.environ["TEST_SRCDIR"],
        os.environ["TEST_WORKSPACE"],
        "packages/biwenger_tools/.claude/skills/draft/scripts",
    )
    if "TEST_SRCDIR" in os.environ
    else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _SCRIPTS)

import archetypes  # noqa: E402
import board  # noqa: E402
import fetch_real_points as frp  # noqa: E402


def player(name, pos="DL", price=1_000_000, sf=300, lines=None, **extra):
    return {
        "name": name,
        "team": extra.get("team", "Equipo"),
        "pos": pos,
        "lines": lines or [pos],
        "price": price,
        "sf": sf,
        # Value per million, as `apply_real_points` derives it. Needed by
        # anything that reaches the captain tiers.
        "vm": extra.get("vm", sf / (price / 1_000_000) if price else 0.0),
        "placeholder": extra.get("placeholder", False),
        "real": extra.get("real"),
        "starts": None,
    }


def held(**by_line):
    """`{line: [rows]}` as `board.main` builds it, from counts or rows."""
    out = {}
    for code, value in by_line.items():
        if isinstance(value, int):
            value = [player(f"{code}{i}", code) for i in range(value)]
        out[code] = [(None, row) for row in value]
    return out


# ---------------------------------------------------------------------------
# Band drain — the metric that shipped inverted
# ---------------------------------------------------------------------------


def test_a_band_nobody_drafts_reads_as_untouched():
    """The bug, pinned. Four of nineteen forwards over 6M were taken, all of
    them early, and dividing by the four made the band read as exhausted at the
    exact pick where fifteen were still available."""
    history = {("DL", "≥ 6M"): [1, 2, 6, 8]}
    supply = {("DL", "≥ 6M"): 19}

    assert archetypes.drain(history, supply, "DL", "≥ 6M", 17) == (4, 19)


def test_drain_counts_only_the_picks_before_your_turn():
    history = {("DF", "3–6M"): [10, 20, 30, 40]}
    supply = {("DF", "3–6M"): 25}

    assert archetypes.drain(history, supply, "DF", "3–6M", 25) == (2, 25)
    assert archetypes.drain(history, supply, "DF", "3–6M", 1) == (0, 25)


def test_drain_is_silent_when_the_band_does_not_exist():
    assert archetypes.drain({}, {}, "PT", "≥ 6M", 10) is None


def test_the_cell_only_shouts_when_the_band_really_emptied():
    assert archetypes.drain_cell(None) == "—"
    assert archetypes.drain_cell((4, 19)) == "4/19"
    assert archetypes.drain_cell((19, 19)) == "**19/19**"


def test_market_supply_counts_every_line_and_band():
    rows = [
        player("a", "DL", 7_000_000),
        player("b", "DL", 6_000_000),
        player("c", "DL", 5_999_999),
        player("d", "DF", 1_000_000),
    ]
    supply = archetypes.band_supply(rows)

    assert supply[("DL", "≥ 6M")] == 2
    assert supply[("DL", "3–6M")] == 1
    assert supply[("DF", "< 1,5M")] == 1


@pytest.mark.parametrize(
    "price,band",
    [
        (6_000_000, "≥ 6M"),
        (5_999_999, "3–6M"),
        (3_000_000, "3–6M"),
        (2_999_999, "1,5–3M"),
        (1_500_000, "1,5–3M"),
        (1_499_999, "< 1,5M"),
        (0, "< 1,5M"),
    ],
)
def test_price_band_boundaries_are_inclusive_at_the_floor(price, band):
    assert archetypes.price_band(price) == band


# ---------------------------------------------------------------------------
# JP's placeholder score — a top-decile number on a 1.5M player
# ---------------------------------------------------------------------------


def test_the_placeholder_spike_is_detected_above_the_median():
    """The spike has to stay a minority of the market — JP hands the default to
    a few dozen players out of ~500, never to half of them."""
    scores = list(range(50, 350, 10)) + [400] * 10

    assert archetypes.detect_placeholder(scores) == 400


def test_no_spike_means_no_placeholder():
    assert archetypes.detect_placeholder(list(range(100, 200))) is None


def test_a_crowd_of_zeroes_does_not_bury_the_spike():
    """Zero-minute players are the most common value in the market, so scanning
    the overall mode first finds them instead of the placeholder."""
    scores = [0] * 60 + [100, 150, 200, 250] + [400] * 12

    assert archetypes.detect_placeholder(scores) == 400


# ---------------------------------------------------------------------------
# The veto file — a name records that somebody was cut, never why
# ---------------------------------------------------------------------------


def test_exclusions_keep_the_reason_beside_the_name(tmp_path):
    path = tmp_path / "vetos.txt"
    path.write_text(
        "# a comment, ignored\n"
        "\n"
        "Valverde   # pelea con el entrenador\n"
        "Villalibre # cero minutos en Primera\n"
        "Sadiq\n",
        encoding="utf-8",
    )

    names, reasons = archetypes.read_exclusions(str(path))

    assert names == ["Valverde", "Villalibre", "Sadiq"]
    assert reasons["Valverde"] == "pelea con el entrenador"
    assert reasons["Sadiq"] == "sin motivo anotado"


def test_exclusions_append_to_the_command_line_ones(tmp_path):
    path = tmp_path / "vetos.txt"
    path.write_text("Valverde # motivo\n", encoding="utf-8")

    names, reasons = archetypes.read_exclusions(str(path), extra=["Pedri"])

    assert names == ["Pedri", "Valverde"]
    assert "Pedri" not in reasons


# ---------------------------------------------------------------------------
# Board — what you can actually afford
# ---------------------------------------------------------------------------


def test_the_cap_reserves_the_slots_you_still_have_to_fill():
    """3M left and four empty slots: the 2.55M forward is affordable only just,
    because a keeper, a defender and a midfielder still have to be paid for."""
    free = [
        player("caro", "DL", 2_550_000),
        player("portero", "PT", 150_000),
        player("defensa", "DF", 150_000),
        player("medio", "MC", 150_000),
    ]
    squad = held(PT=0, DF=4, MC=4, DL=3)

    cap = board.spend_cap(free, squad, "DL", 3_000_000)

    assert cap == 2_550_000  # 3M minus three 150k reservations


def test_a_full_line_reserves_nothing_for_itself():
    free = [player("x", "PT", 900_000), player("y", "DF", 900_000)]
    squad = held(PT=2, DF=5, MC=5, DL=3)

    assert board.spend_cap(free, squad, "DL", 1_000_000) == 1_000_000


def test_the_cap_reserves_one_price_per_missing_slot():
    free = [player(f"df{i}", "DF", 100_000 * (i + 1)) for i in range(5)]
    squad = held(PT=2, DF=0, MC=5, DL=3)

    # Five defenders missing, cheapest five cost 100k+200k+300k+400k+500k.
    assert board.spend_cap(free, squad, "DL", 3_000_000) == 3_000_000 - 1_500_000


def test_the_cap_counts_a_multi_position_player_in_every_line_he_covers():
    """Five midfielders who also play at the back are not a defensive hole, and
    reserving money to fill one refuses purchases that were affordable."""
    free = [player(f"df{i}", "DF", 500_000) for i in range(5)]
    hybrids = [player(f"h{i}", "MC", lines=["MC", "DF"]) for i in range(5)]
    strict = held(PT=2, DF=0, MC=hybrids, DL=3)

    assert board.spend_cap(free, strict, "DL", 3_000_000) == 3_000_000


def test_your_picks_zigzag_with_the_snake():
    assert board.my_picks(3, 7, 4) == [3, 12, 17, 26]
    assert board.my_picks(1, 7, 3) == [1, 14, 15]
    assert board.my_picks(7, 7, 3) == [7, 8, 21]


def test_a_placeholder_is_returned_unscored():
    """JP's default is a top-decile number attached to a 1.5M player. Scoring it
    puts a player nobody has data for at the head of the list."""
    assert board.points(player("x", placeholder=True))[0] is None
    assert board.points(player("x", placeholder=True))[1] == "🎲"


def test_measured_points_outrank_the_projection():
    assert board.points(player("x", sf=300, real=77)) == (77, "✅")
    assert board.points(player("x", sf=300))[1] == "~"


def test_availability_is_counted_against_the_market():
    market = {
        "uno": player("Uno", "DL", 7_000_000),
        "dos": player("Dos", "DL", 7_000_000),
        "tres": player("Tres", "DL", 7_000_000),
    }
    picks = [{"player_name": "Uno"}]

    assert board.availability(market, picks, "DL", "≥ 6M") == (2, 3)


def test_availability_is_none_for_an_empty_band():
    assert board.availability({}, [], "PT", "≥ 6M") is None


# ---------------------------------------------------------------------------
# Personalizado — this league's scoring, not SofaScore
# ---------------------------------------------------------------------------


# `fetch_real_points` only names the two positions whose clean sheet pays.
MID, FWD = 3, 4


def match(score, minutes=90, **flags):
    return {"rawStats": {"score2": score, "minutesPlayed": minutes, **flags}}


def test_playing_and_winning_each_pay_a_point():
    result = frp.personalizado([match(10, win=True)], MID)

    assert result["points"] == 12  # 10 base + 1 played + 1 win


def test_a_substitute_collects_neither_bonus():
    """The bonuses gate on more than 65 minutes, which is why a total earned off
    the bench does not transfer to a starting slot."""
    result = frp.personalizado([match(10, minutes=50, win=True)], MID)

    assert result["points"] == 10
    assert result["starts"] == 0


def test_counting_a_start_and_paying_the_bonus_use_different_thresholds():
    """Deliberate, and easy to "tidy" into a bug: 60 minutes is the heuristic for
    having started, 65 is the league's own gate for the play and win bonuses."""
    result = frp.personalizado([match(10, minutes=62, win=True)], MID)

    assert result["starts"] == 1
    assert result["points"] == 10


def test_a_clean_sheet_pays_the_keeper_double_the_defender():
    keeper = frp.personalizado([match(6, cleanSheet=True)], frp.GK)
    defender = frp.personalizado([match(6, cleanSheet=True)], frp.DEF)
    forward = frp.personalizado([match(6, cleanSheet=True)], FWD)

    assert keeper["points"] - forward["points"] == 2
    assert defender["points"] - forward["points"] == 1


def test_cards_penalties_and_defeats_subtract():
    assert frp.personalizado([match(10, yellowCard=1)], MID)["points"] == 10
    assert frp.personalizado([match(10, lost=True)], MID)["points"] == 10
    assert frp.personalizado([match(10, penaltyMissed=1)], MID)["points"] == 9


def test_a_match_without_minutes_is_not_a_match():
    result = frp.personalizado([match(0, minutes=0), match(8)], MID)

    assert result["games"] == 1
    assert result["points"] == 9


def test_the_star_flag_is_deliberately_ignored():
    """Treating it as the config's MVP bonus overshoots both controls."""
    plain = frp.personalizado([match(10)], MID)
    starred = frp.personalizado([match(10, star=True)], MID)

    assert plain["points"] == starred["points"]


# ---------------------------------------------------------------------------
# Squad shapes — the generator used to fill one hardcoded 2-5-5-3
# ---------------------------------------------------------------------------


def test_formations_come_from_production_not_a_second_list():
    """The two lists had drifted: this file knew seven, production knew more,
    and the shapes the real squad plays were invisible to the generator."""
    from packages.biwenger_tools.api.logic.lineup import FORMATIONS as prod

    assert archetypes.FORMATIONS == tuple((d, m, f) for _label, d, m, f in prod)


def test_every_viable_shape_is_an_eleven_plus_a_bench_of_every_line():
    for shape in archetypes.viable_shapes():
        assert sum(shape.values()) == archetypes.SQUAD_SIZE
        outfield = (shape["DF"], shape["MC"], shape["DL"])
        assert any(
            outfield == (d + 1, m + 1, f + 1) for d, m, f in archetypes.FORMATIONS
        ), archetypes.shape_label(shape)
    assert len(archetypes.viable_shapes()) == len(archetypes.FORMATIONS)


def test_the_shapes_the_real_squads_play_are_reachable():
    """2-5-5-3 is the classic (4-4-2); 2-5-7-1 is the 4-6-0 the 26-27 squad
    plays, with its forward on the bench."""
    shapes = archetypes.viable_shapes()
    assert {"PT": 2, "DF": 5, "MC": 5, "DL": 3} in shapes
    assert {"PT": 2, "DF": 5, "MC": 7, "DL": 1} in shapes
    assert {"PT": 2, "DF": 5, "MC": 8, "DL": 0} not in shapes


def test_the_draft_carries_two_keepers():
    assert all(s["PT"] == 2 for s in archetypes.viable_shapes())
    assert archetypes.NEED["PT"] == 2


def test_the_reserve_keeper_is_the_cheapest_and_never_upgraded():
    """The draft requires a second keeper; nobody fields him and he is sold
    once it closes, so every euro on him is a euro off the eleven."""
    rows = (
        [player("Cheap", "PT", 150_000, 100), player("Mid", "PT", 900_000, 300)]
        + [player("Star", "PT", 5_000_000, 600)]
        + [player(f"D{i}", "DF", 1_000_000, 300) for i in range(5)]
        + [player(f"M{i}", "MC", 1_000_000, 400) for i in range(5)]
        + [player(f"F{i}", "DL", 1_000_000, 350) for i in range(3)]
    )
    squad, _, _ = archetypes.build(rows, 20_000_000)
    assert {r["name"] for r in squad["PT"]} == {"Cheap", "Star"}


def test_searching_shapes_never_scores_below_the_fixed_one():
    """The classic shape is in the search space, so the winner is at least as
    good — the property that makes this refactor safe to adopt by default."""
    rows = (
        [player(f"P{i}", "PT", 1_000_000, 200 + i) for i in range(4)]
        + [player(f"D{i}", "DF", 1_000_000, 300 + i) for i in range(9)]
        + [player(f"M{i}", "MC", 1_000_000, 400 + i) for i in range(9)]
        + [player(f"F{i}", "DL", 1_000_000, 350 + i) for i in range(9)]
    )
    budget = 20_000_000
    fixed, _, _ = archetypes.build(rows, budget)
    best, _, _, shape = archetypes.build_best_shape(rows, budget)

    assert archetypes.shape_score(best) >= archetypes.shape_score(fixed)
    assert sum(len(best[c]) for c in archetypes.POS) == archetypes.SQUAD_SIZE
    assert archetypes.squad_is_legal(best), archetypes.shape_label(shape)


def test_a_shape_the_pool_cannot_fill_is_never_the_winner():
    """A legal eleven is not a fifteen: a shape asking for more of a line than
    the pool holds used to win with a player missing."""
    rows = (
        [player(f"P{i}", "PT", 1_000_000, 200) for i in range(2)]
        + [player(f"D{i}", "DF", 1_000_000, 300) for i in range(5)]
        + [player(f"M{i}", "MC", 1_000_000, 400) for i in range(5)]
        + [player(f"F{i}", "DL", 1_000_000, 350) for i in range(4)]
    )
    best, _, _, _ = archetypes.build_best_shape(rows, 20_000_000)
    assert sum(len(best[c]) for c in archetypes.POS) == archetypes.SQUAD_SIZE


def test_build_honours_a_requested_shape():
    rows = (
        [player(f"P{i}", "PT", 1_000_000, 200) for i in range(4)]
        + [player(f"D{i}", "DF", 1_000_000, 300) for i in range(9)]
        + [player(f"M{i}", "MC", 1_000_000, 400) for i in range(9)]
        + [player(f"F{i}", "DL", 1_000_000, 350) for i in range(9)]
    )
    shape = {"PT": 2, "DF": 5, "MC": 7, "DL": 1}
    squad, _, _ = archetypes.build(rows, 20_000_000, shape=shape)
    assert {c: len(squad[c]) for c in archetypes.POS} == shape


# --- the starts penalty: a cameo total is not a season -------------------


def _row(name, sf, starts, pos="DEL", price=1_000_000, team="X"):
    return {
        "name": name,
        "sf": sf,
        "starts": starts,
        "pos": pos,
        "price": price,
        "team": team,
        "sofascore": sf,
    }


def test_without_the_penalty_a_cameo_total_outranks_a_regular():
    """Today's behaviour, and the reason the item exists: Aspas scored 143
    across 32 appearances having started 10, and outbids a regular starter."""
    cameo = _row("Aspas", sf=143, starts=10)
    regular = _row("Titular", sf=130, starts=34)
    assert archetypes.ranking_score(cameo) > archetypes.ranking_score(regular)


def test_with_the_penalty_the_regular_wins():
    archetypes.set_starts_penalty(True)
    try:
        cameo = _row("Aspas", sf=143, starts=10)
        regular = _row("Titular", sf=130, starts=34)
        assert archetypes.ranking_score(regular) > archetypes.ranking_score(cameo)
    finally:
        archetypes.set_starts_penalty(False)


def test_a_full_season_is_never_penalised():
    """At or above the threshold the score is untouched — the penalty
    discounts a total built on cameos, it does not tax playing."""
    archetypes.set_starts_penalty(True)
    try:
        regular = _row("Titular", sf=130, starts=archetypes.STARTER_THRESHOLD)
        assert archetypes.ranking_score(regular) == 130
    finally:
        archetypes.set_starts_penalty(False)


def test_unknown_starts_are_not_penalised():
    """Same rule `is_starter` already applies: no measured data means the
    projection already assumes a regular role, and penalising it would
    silently drop every player promoted from Segunda."""
    archetypes.set_starts_penalty(True)
    try:
        promoted = _row("Ascendido", sf=100, starts=None)
        assert archetypes.ranking_score(promoted) == 100
    finally:
        archetypes.set_starts_penalty(False)


def test_the_penalty_is_off_by_default():
    """The draft is annual and irreversible. Nothing changes until the flag
    is passed deliberately."""
    cameo = _row("Aspas", sf=143, starts=10)
    assert archetypes.ranking_score(cameo) == 143


# --- the projection production reads, and who can play --------------------


_RANKED_COLS = (
    "id,name,team,position,alt_positions,price,sofascore,projection,oraculo,"
    "availability,uncalled,fixtures,value_per_m,no_jp_data,jp_placeholder"
)


def _ranked(tmp_path, *lines, header=_RANKED_COLS):
    path = tmp_path / "ranked.csv"
    path.write_text("\n".join([header, *lines]) + "\n", encoding="utf-8")
    return str(path)


def test_load_ranks_on_the_blend_and_keeps_jp_beside_it(tmp_path):
    """Auto-bid, the trader and the digest all read the JP + Oráculo blend;
    a draft on JP alone bought a different fifteen from the one the season
    then judges."""
    path = _ranked(
        tmp_path,
        "1,A,X,DL,DL,2000000,400,460,True,plays,False,fácil 30,200,False,False",
    )
    (row,), _, _ = archetypes.load(path, exclude=())
    assert row["sf"] == 460 and row["sf_jp"] == 400


def test_load_reads_an_old_csv_on_jp_alone(tmp_path):
    path = _ranked(
        tmp_path,
        "A,X,DL,DL,2000000,400,200,False,False",
        header="name,team,position,alt_positions,price,sofascore,value_per_m,"
        "no_jp_data,jp_placeholder",
    )
    (row,), _, _ = archetypes.load(path, exclude=())
    assert row["sf"] == 400 and row["sf_jp"] == 400


def test_load_drops_who_cannot_play_unless_kept(tmp_path):
    path = _ranked(
        tmp_path,
        "1,Fit,X,DL,DL,2000000,400,400,False,plays,False,—,200,False,False",
        "2,Hurt,X,DL,DL,2000000,500,500,False,out,False,—,250,False,False",
    )
    kept, _, _ = archetypes.load(path, exclude=())
    assert [r["name"] for r in kept] == ["Fit"]
    assert [r["name"] for r in archetypes.unavailable(path)] == ["Hurt"]
    kept, _, _ = archetypes.load(path, exclude=(), keep_unavailable=True)
    assert {r["name"] for r in kept} == {"Fit", "Hurt"}


def test_the_projection_column_is_filled_without_real_points(tmp_path):
    """It printed "—" for every player unless last season's points were
    fetched, so the sheet hid the one number it always had."""
    path = _ranked(
        tmp_path,
        "1,A,X,DL,DL,2000000,400,460,True,plays,False,fácil 30,200,False,False",
    )
    (row,), _, _ = archetypes.load(path, exclude=())
    assert archetypes.data_cells(row).startswith("| 460 ")
    assert row["fixtures"] == "fácil 30"


def test_the_club_cap_defaults_to_production_s():
    from packages.biwenger_tools.api import config

    assert archetypes.DEFAULT_MAX_PER_TEAM == config.MAX_PLAYERS_PER_CLUB


def test_rank_carries_the_blend_availability_and_the_fixtures(tmp_path):
    import draft_ranking as dr

    csv_path = tmp_path / "market.csv"
    csv_path.write_text(
        "Equipo;Jugador;Posición;Puntos;Precio\nX;Ana;Delantero;10;2000000\n"
        "X;Bea;Defensa;5;1000000\n",
        encoding="utf-8-sig",
    )
    competition = {
        "players": {
            "7": {
                "id": 7,
                "name": "Ana",
                "position": 4,
                "altPositions": [3],
                "teamID": 3,
                "price": 2_000_000,
            },
            "8": {
                "id": 8,
                "name": "Bea",
                "position": 2,
                "teamID": 3,
                "price": 1_000_000,
            },
        }
    }
    jp = [
        {
            "name": "Ana",
            "slug": "ana",
            "status": "ok",
            "nextMatch": {"status": "pending", "playerInLineup": True},
            "predict": [{"type": 2, "rate": 450}],
        },
        {
            "name": "Bea",
            "slug": "bea",
            "status": "injured",
            "nextMatch": {"status": "pending", "playerInLineup": False},
            "predict": [{"type": 2, "rate": 300}],
        },
    ]
    rows = dr.rank(
        str(csv_path),
        jp,
        competition=competition,
        upcoming={3: [30, 40, 50]},
        rises={7: 0.25},
    )
    by = {r["name"]: r for r in rows}
    assert by["Ana"]["id"] == 7 and by["Ana"]["alt_positions"] == "DL/MC"
    assert by["Ana"]["projection"] == 450 and by["Ana"]["oraculo"] is False
    assert by["Ana"]["availability"] == "plays" and by["Ana"]["fixtures"] == "fácil 40"
    assert by["Bea"]["availability"] == "out" and by["Bea"]["uncalled"] is True
    assert by["Ana"]["rise"] == 0.25 and by["Bea"]["rise"] is None


def test_risers_read_the_stored_daily_prices():
    """`price_snapshots` already holds every player's price each day; two
    exports by hand were the only way to see a rise before."""
    import risers

    days = [{7: 1_000_000, 8: 2_000_000}, {7: 1_100_000}, {7: 1_300_000, 8: 1_900_000}]
    assert risers.span_from_snapshots(days) == {
        7: (1_000_000, 1_300_000),
        8: (2_000_000, 1_900_000),
    }


def test_a_report_without_its_competition_still_counts():
    """The player endpoint is LaLiga's, and Biwenger stopped expanding
    `match.competition`: filtering on it threw away every match and published
    thirty players as having no minutes in Primera."""
    bare = {"match": {"id": 1}, "rawStats": {"minutesPlayed": 90}}
    cup = {"match": {"competition": {"slug": "copa-del-rey"}}, "rawStats": {}}
    league = {"match": {"competition": {"slug": "la-liga"}}, "rawStats": {}}
    assert frp.league_reports([bare, cup, league]) == [bare, league]


def test_load_skips_a_row_without_a_known_line(tmp_path):
    """A row with no line used to load and then crash the real-points
    calibration, which keys its factors by line."""
    path = _ranked(
        tmp_path,
        "1,A,X,DL,DL,2000000,400,400,False,plays,False,—,200,False,False",
        "2,B,X,,,2000000,400,400,False,plays,False,—,200,False,False",
    )
    kept, _, _ = archetypes.load(path, exclude=())
    assert [r["name"] for r in kept] == ["A"]


def test_the_season_biwenger_serves_is_read_from_the_selected_flag():
    """`reports` carry the season Biwenger has selected, with no parameter to
    ask for another: in pre-season that must still be last season's, and the
    script has to notice when it is not."""
    seasons = [
        {"slug": "2026-2027", "games": 0, "selected": True},
        {"slug": "2025-2026", "games": 35},
    ]
    assert frp.served_season(seasons) == "2026-2027"
    assert frp.served_season([{"slug": "2025-2026"}]) is None


# --- what the backtest of 26-27 taught -------------------------------------


def test_shapes_are_judged_on_the_fifteen_not_the_eleven():
    """Backtested on 26-27: the build the XI metric ranked first (bench at the
    floor) finished fifth of six in real points, because injuries and rotation
    put the bench on the pitch. The whole fifteen ranked them far closer."""
    deep = {
        "PT": [player("K1", "PT", sf=300), player("K2", "PT", sf=10)],
        "DF": [player(f"D{i}", "DF", sf=300) for i in range(5)],
        "MC": [player(f"M{i}", "MC", sf=300) for i in range(5)],
        "DL": [player(f"F{i}", "DL", sf=300) for i in range(3)],
    }
    assert archetypes.shape_score(deep) == archetypes.durable_eff(deep)


def test_momentum_lifts_a_riser_and_leaves_a_faller_alone():
    rows = [
        dict(player("Up", sf=400), rise=0.20),
        dict(player("Down", sf=400), rise=-0.10),
        player("Flat", sf=400),
    ]
    boosted = {r["name"]: r["sf"] for r in archetypes.momentum_rows(rows)}
    assert boosted["Up"] > 400 and boosted["Down"] == 400 and boosted["Flat"] == 400
    assert [r["sf"] for r in rows] == [400, 400, 400]  # copies, not the originals


def test_the_strong_keeper_is_the_best_scorer_under_the_cap():
    rows = [
        player("Cheap", "PT", 1_000_000, 300),
        player("Best", "PT", 4_000_000, 450),
        player("Star", "PT", 9_000_000, 600),
        player("Field", "DF", 1_000_000, 900),
    ]
    assert archetypes.strong_keeper(rows)["name"] == "Best"


def test_ranked_csv_carries_the_price_rise_into_the_rows(tmp_path):
    path = _ranked(
        tmp_path,
        "1,A,X,DL,DL,2000000,400,400,False,plays,False,—,0.125,200,False,False",
        header=_RANKED_COLS.replace("fixtures,", "fixtures,rise,"),
    )
    (row,), _, _ = archetypes.load(path, exclude=())
    assert row["rise"] == 0.125


# --- tiers, starts and rivals ----------------------------------------------


def test_the_start_rate_is_over_the_rounds_the_sample_covers():
    """Nine rounds in, seven starts is a regular starter; over 38 it read as a
    substitute and every measured player got the 🪑."""
    row = dict(player("A"), starts=7, rounds=9)
    assert archetypes.start_rate(row) == 7 / 9
    assert archetypes.is_starter(row) is True
    assert archetypes.is_starter(dict(row, starts=3)) is False


def test_real_points_carry_the_rounds_they_cover(tmp_path):
    path = tmp_path / "real.csv"
    path.write_text("name,points,games,starts\nA,60,9,8\nB,20,4,2\n", encoding="utf-8")
    real = archetypes.read_real_points(str(path))
    assert real["a"]["rounds"] == 9 and real["b"]["rounds"] == 9


def test_tiers_are_league_sized_and_ranked_by_points_per_round():
    import tiers

    rows = [player(f"D{i}", "DF", sf=100 + i) for i in range(16)]
    out = tiers.build_tiers(rows, managers=7, rounds=10)
    assert [len(t) for t in out["DF"]] == [7, 7, 2]
    assert out["DF"][0][0]["name"] == "D15"
    assert out["DF"][0][0]["per_round"] == 11.5


def test_the_window_counts_lines_picked_between_two_turns():
    import tiers

    history = [
        {"pick": 3, "line": "DL"},
        {"pick": 5, "line": "DF"},
        {"pick": 8, "line": "DF"},
        {"pick": 11, "line": "MC"},
        {"pick": 12, "line": "PT"},
    ]
    assert tiers.window_lines(history, 3, 12) == {"DF": 2, "MC": 1}


def test_rival_profiles_read_spend_and_lines_by_round():
    import tiers

    picks = [
        {"manager_name": "Ana", "global_pick": 1, "round": 1, "price": 13_000_000},
        {"manager_name": "Ana", "global_pick": 14, "round": 2, "price": 7_000_000},
        {"manager_name": "Ana", "global_pick": 15, "round": 15, "price": 150_000},
    ]
    lines = {1: "DL", 14: "MC", 15: "PT"}
    (profile,) = tiers.rival_profiles(picks, lines)
    assert profile["manager"] == "Ana"
    assert profile["first"] == 13_000_000
    assert profile["first_lines"] == "DL MC PT"
    assert profile["cheap"] == 1


def test_the_board_counts_what_survives_of_each_tier():
    """Mid-draft the question is how much of tier A is still free, against
    how many picks land before your turn."""
    market = [
        dict(player(f"D{i}", "DF", sf=100 + i), real=None, placeholder=False)
        for i in range(10)
    ]
    taken = {"d9", "d8", "d0"}
    survival = board.tier_survival(market, taken, managers=7)
    assert survival["DF"] == [("A", 5, 7), ("B", 2, 3)]


# --- asking Biwenger for a season by name --------------------------------


def test_the_season_parameter_is_the_year_the_season_ends():
    """`season=2026` returns 2025/26's reports (verified on Ryan: 36 games,
    J3-J38, 2025-2026 `selected`), whatever season Biwenger is showing."""
    assert frp.season_id("2025-2026") == "2026"
    url = frp.player_url("ryan", "2025-2026")
    assert "season=2026" in url and "/players/la-liga/ryan?" in url


def test_the_cache_keeps_each_season_apart(tmp_path):
    """The same player in two seasons is two answers; one cache file each."""
    fetcher = frp.Fetcher(str(tmp_path), delay=0, max_requests=0, season="2025-2026")
    other = frp.Fetcher(str(tmp_path), delay=0, max_requests=0, season="2026-2027")
    assert fetcher.cache_path("ryan") != other.cache_path("ryan")


def test_the_season_row_is_laliga_s_not_another_competition_s():
    seasons = [
        {"slug": "2025-2026", "games": 0, "competition": {"slug": "serie-a"}},
        {"slug": "2025-2026", "games": 36, "selected": True},
    ]
    assert frp._season_row(seasons, "2025-2026")["games"] == 36
    assert frp.served_season(seasons) == "2025-2026"


# --- what the mock draft of 22/10 taught -----------------------------------


def test_value_trusts_a_measured_total_over_a_projection_and_charges_price():
    import tiers

    measured = dict(player("M", price=2_000_000, sf=190), pr=5.0, source="real")
    projected = dict(measured, name="P", source="proj")
    new = dict(projected, name="N", no_primera=True)
    pricey = dict(measured, name="X", price=8_000_000)
    values = [tiers.pick_value(r) for r in (measured, projected, new, pricey)]
    assert values[0] > values[1] > values[2]
    assert values[0] > values[3]


def test_the_shortlist_proposes_the_unmeasured_of_the_plan_keepers_first():
    """A keeper's projection cannot see he is the backup — Aitor Fernández,
    Fortuño: one start in 38 each. Every keeper in reach is measured first."""
    import tiers

    rows = [
        dict(player("K", "PT", sf=200), pr=5.0, source="proj"),
        dict(player("D", "DF", sf=300), pr=6.0, source="proj"),
        dict(player("R", "DF", sf=300), pr=6.0, source="real"),
    ]
    assert tiers.shortlist(rows, limit=2) == ["K", "D"]


def test_players_without_primera_minutes_are_marked_not_dropped(tmp_path):
    path = tmp_path / "real.csv"
    path.write_text(
        "name,points,games,starts,no_primera\nA,60,30,25,\nB,,,,True\n",
        encoding="utf-8",
    )
    assert archetypes.read_no_primera(str(path)) == {"b"}
    row = dict(player("B"), sf=300)
    archetypes.apply_real_points(
        [row], archetypes.read_real_points(str(path)), new={"b"}
    )
    assert row["no_primera"] is True and archetypes.source_cell(row) == "🆕"


def test_the_mock_keeps_the_reserve_keeper_for_last_and_caps_the_price():
    import mock_draft

    rows = (
        [dict(player(f"K{i}", "PT", 150_000 + i, 100 + i)) for i in range(5)]
        + [dict(player("Star", "MC", 20_000_000, 900))]
        + [dict(player(f"D{i}", "DF", 1_000_000, 300 + i)) for i in range(11)]
        + [dict(player(f"M{i}", "MC", 1_000_000, 300 + i)) for i in range(11)]
        + [dict(player(f"F{i}", "DL", 1_000_000, 300 + i)) for i in range(8)]
    )
    for r in rows:
        r["pr"] = r["sf"] / 38
        r["source"] = "real"
    squads, log = mock_draft.simulate(
        rows, order=["A", "Me"], me="Me", budget=40_000_000, habits={}, history=[]
    )
    mine = squads["Me"]
    assert "Star" not in {r["name"] for r in mine}
    assert sum(1 for r in mine if r["pos"] == "PT") == 2
    assert mine[-1]["pos"] == "PT"


def test_the_mock_keeps_money_for_a_bench_that_plays():
    """Every slot but the reserve keeper's keeps DEPTH_RESERVE back, so the
    last outfield picks are players who score, not 0.15M fillers."""
    import mock_draft

    rows = (
        [dict(player(f"K{i}", "PT", 150_000 + i, 100 + i)) for i in range(5)]
        + [dict(player(f"D{i}", "DF", 1_200_000, 150 + i)) for i in range(11)]
        + [dict(player(f"M{i}", "MC", 1_200_000, 150 + i)) for i in range(11)]
        + [dict(player(f"F{i}", "DL", 1_200_000, 150 + i)) for i in range(8)]
        + [dict(player(f"Z{i}", "MC", 150_000, 5)) for i in range(6)]
        + [dict(player(f"S{i}", "MC", 6_000_000, 400 + i)) for i in range(6)]
    )
    for r in rows:
        r["pr"] = r["sf"] / 38
        r["source"] = "real"
    squads, _ = mock_draft.simulate(
        rows, order=["A", "Me"], me="Me", budget=30_000_000, habits={}, history=[]
    )
    outfield = [r for r in squads["Me"] if r["pos"] != "PT"]
    assert all(not r["name"].startswith("Z") for r in outfield)


# --- the season folder: the plan, what was drafted, then analysis and data ---


def test_a_season_file_in_a_subfolder_gets_its_folder(tmp_path, monkeypatch):
    import paths

    monkeypatch.setenv("DRAFT_OUT_ROOT", str(tmp_path))
    path = paths.season_path("27-28", paths.RANKED)
    assert path == str(tmp_path / "27-28" / "datos" / "draft-ranked.csv")
    assert (tmp_path / "27-28" / "datos").is_dir()


def test_the_plan_and_what_was_drafted_sit_at_the_top_of_the_season():
    import paths

    assert paths.DECISION == "plan.md"
    assert paths.MY_DRAFT == "mi-draft.md"
    assert paths.AVAILABILITY == "historial.md"
    for name in (paths.RANKED, paths.REAL_POINTS, paths.AVAILABILITY_CSV):
        assert name.startswith("datos/")
    for name in (paths.ARCHETYPES, paths.TIERS, paths.REHEARSAL):
        assert name.startswith("analisis/")


def test_my_draft_lists_only_my_picks_with_what_they_cost():
    import availability_report

    picks = [
        {
            "global_pick": 3,
            "round": 1,
            "manager_name": "Jorge",
            "player_name": "Olmo",
            "player_team": "Barcelona",
            "line": "MC",
            "price": 11_250_000,
        },
        {
            "global_pick": 4,
            "round": 1,
            "manager_name": "Manu",
            "player_name": "X",
            "player_team": "Y",
            "line": "DL",
            "price": 1,
        },
        {
            "global_pick": 12,
            "round": 2,
            "manager_name": "Jorge",
            "player_name": "Dmitrovic",
            "player_team": "Espanyol",
            "line": "PT",
            "price": 3_970_000,
        },
    ]
    text = availability_report.render_mine(picks, "26-27", "Jorge")
    assert "Olmo" in text and "Dmitrovic" in text and "| X |" not in text
    assert "2 jugadores" in text and "15,22M" in text
