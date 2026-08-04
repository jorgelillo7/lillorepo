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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import archetypes  # noqa: E402
import board  # noqa: E402
import fetch_real_points as frp  # noqa: E402


def player(name, pos="DL", price=1_000_000, sf=300, **extra):
    return {
        "name": name,
        "team": extra.get("team", "Equipo"),
        "pos": pos,
        "price": price,
        "sf": sf,
        "placeholder": extra.get("placeholder", False),
        "real": extra.get("real"),
        "starts": None,
    }


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
    """3M left and four empty slots: the 2.55M forward is not affordable, because
    a keeper, a defender and a midfielder still have to be paid for."""
    free = [
        player("caro", "DL", 2_550_000),
        player("portero", "PT", 150_000),
        player("defensa", "DF", 150_000),
        player("medio", "MC", 150_000),
    ]
    held = {"PT": [1], "DF": [1, 2, 3, 4], "MC": [1, 2, 3, 4], "DL": [1, 2]}

    cap = board.spend_cap(free, held, "DL", 3_000_000)

    assert cap == 2_550_000  # 3M minus three 150k reservations


def test_a_full_line_reserves_nothing_for_itself():
    free = [player("x", "PT", 900_000), player("y", "DF", 900_000)]
    held = {"PT": [1, 2], "DF": [1, 2, 3, 4, 5], "MC": [1] * 5, "DL": [1, 2, 3]}

    assert board.spend_cap(free, held, "DL", 1_000_000) == 1_000_000


def test_the_cap_reserves_one_price_per_missing_slot():
    free = [player(f"df{i}", "DF", 100_000 * (i + 1)) for i in range(5)]
    held = {"PT": [1, 2], "DF": [], "MC": [1] * 5, "DL": [1, 2, 3]}

    # Five defenders missing, cheapest five cost 100k+200k+300k+400k+500k.
    assert board.spend_cap(free, held, "DL", 3_000_000) == 3_000_000 - 1_500_000


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
