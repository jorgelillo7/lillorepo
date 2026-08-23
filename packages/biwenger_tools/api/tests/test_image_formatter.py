"""Unit tests for `api/logic/image_formatter.build_table_image`."""

from packages.biwenger_tools.api.logic.image_formatter import (
    _BENCH,
    _BENCH_BG,
    _MARK_BENCH,
    _MARK_OUT,
    _MARK_STARTS,
    _mark,
    _row_bg,
    _strip_emoji,
    build_table_image,
    total_value,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_build_table_image_renders_placeholder_on_empty_rows():
    """An empty squad/market (post league-reset) must render a placeholder
    PNG instead of crashing inside matplotlib's ax.table."""
    png = build_table_image([], "Mi equipo")
    assert png.startswith(PNG_MAGIC)


def test_build_table_image_renders_rows():
    rows = [
        {"name": "Lamine Yamal", "position_id": 4, "price": 24_500_000},
        {"name": "Vinicius", "position_id": 4, "price": 20_000_000},
    ]
    png = build_table_image(rows, "Mercado")
    assert png.startswith(PNG_MAGIC)


def test_total_value_sums_the_cf_base_prices():
    """The header figure must match the Precio column it sits above: the
    cf-base price, which is also what `/comparar` ranks managers by."""
    rows = [{"price": 7_400_000}, {"price": 6_500_000}, {"price": 100_000}]
    assert total_value(rows) == "14M"


def test_total_value_keeps_one_decimal_when_there_is_one():
    rows = [{"price": 7_400_000}, {"price": 3_300_000}]
    assert total_value(rows) == "10.7M"


def test_total_value_survives_rows_without_a_price():
    """A row can reach the renderer with no price — an unknown cf-base value
    is 0 elsewhere in this module, and must not blow up the header."""
    assert total_value([{"price": None}, {}, {"price": 2_000_000}]) == "2M"


def test_build_table_image_renders_with_the_total_shown():
    rows = [{"name": "Canales", "position_id": 3, "price": 7_400_000}]
    assert build_table_image(rows, "Mi equipo", show_total_value=True).startswith(
        PNG_MAGIC
    )


def test_strip_emoji_leaves_nothing_of_a_two_codepoint_icon():
    """`🛡️` is the shield (above the BMP) plus U+FE0F. Dropping only the
    astral half left the selector orphaned, and matplotlib draws an orphaned
    modifier as a dotted-circle placeholder — the stray glyph that used to sit
    where the squad image's icon should have been."""
    assert _strip_emoji("🛡️ Mi equipo") == "Mi equipo"


def test_strip_emoji_handles_the_icons_that_never_broke():
    """`👤` and `🛒` carry no variation selector, which is why only the squad
    title showed the artefact. They must keep working."""
    assert _strip_emoji("👤 Ruben") == "Ruben"
    assert _strip_emoji("🛒 Mercado") == "Mercado"


def test_strip_emoji_keeps_accented_text():
    """Stripping must not reach ordinary Latin-1 — manager names carry it."""
    assert _strip_emoji("👤 Expósito") == "Expósito"


# --- Suplentes: the third channel -----------------------------------------


def _jp(*, in_xi=True, status="ok", fixture="pending"):
    return {
        "status": status,
        "nextMatch": {"status": fixture, "playerInLineup": in_xi},
    }


def test_mark_distinguishes_starter_bench_and_out():
    assert _mark(_jp()) == _MARK_STARTS
    assert _mark(_jp(in_xi=False)) == _MARK_BENCH
    assert _mark(_jp(status="injured")) == _MARK_OUT


def test_an_injured_substitute_reads_as_out_not_as_bench():
    """Two marks for one player is how a reader stops trusting the column,
    and "no juega" is the news that matters about him."""
    injured_sub = _jp(in_xi=False, status="injured")
    assert _mark(injured_sub) == _MARK_OUT
    assert _row_bg(injured_sub) != _BENCH_BG


def test_bench_row_gets_its_own_tint():
    assert _row_bg(_jp(in_xi=False)) == _BENCH_BG
    assert _row_bg(_jp()) != _BENCH_BG


def test_bench_amber_is_not_reused_by_any_other_channel():
    """The reserved-hue rule: amber means "empieza en el banquillo" and
    nothing else, or the table teaches the reader a colour that lies."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    assert _BENCH not in imf._BAND_FG.values()
    assert _BENCH not in (imf._CRITICAL, imf._GOOD)


def test_markers_survive_the_emoji_stripper():
    """matplotlib draws a dotted-circle placeholder for anything above the
    BMP, which is why these are geometric glyphs and not a 🪑."""
    for mark in (_MARK_STARTS, _MARK_BENCH, _MARK_OUT):
        assert _strip_emoji(mark) == mark


def test_build_table_image_renders_a_squad_with_substitutes():
    rows = [
        {"name": "Titular", "position_id": 1, "price": 5_000_000, "jp_player": _jp()},
        {
            "name": "Suplente",
            "position_id": 3,
            "price": 1_000_000,
            "jp_player": _jp(in_xi=False),
        },
        {
            "name": "Lesionado",
            "position_id": 2,
            "price": 2_000_000,
            "jp_player": _jp(status="injured"),
        },
    ]
    assert build_table_image(rows, "Mi equipo", show_total_value=True).startswith(
        PNG_MAGIC
    )


def test_a_doubt_is_not_marked_as_a_certain_starter():
    """JP's `doubt` is not in CANNOT_PLAY — he may well play, so calling him
    unavailable would be wrong. Marking him a certain starter is the opposite
    error, and the one a reader acts on."""
    doubtful = _jp(status="doubt")
    assert _mark(doubtful) == _MARK_BENCH
    assert _row_bg(doubtful) == _BENCH_BG


def test_a_doubt_still_counts_among_the_players_who_can_play():
    """He is fit; only the marker channel reports the uncertainty."""
    from packages.biwenger_tools.api.player_formatting import (
        availability,
        count_availability,
    )

    assert availability(_jp(status="doubt")) == "plays"
    plays, out, _ = count_availability([{"jp_player": _jp(status="doubt")}])
    assert (plays, out) == (1, 0)


def test_bench_count_covers_both_ways_of_not_starting():
    from packages.biwenger_tools.api.player_formatting import count_bench

    rows = [
        {"jp_player": _jp()},
        {"jp_player": _jp(in_xi=False)},
        {"jp_player": _jp(status="doubt")},
        {"jp_player": _jp(status="injured")},
    ]
    assert count_bench(rows) == 2
