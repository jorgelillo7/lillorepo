"""Unit tests for `api/logic/image_formatter.build_table_image`."""

import io
from datetime import datetime

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


def test_the_image_is_stamped_with_when_it_was_made():
    """These arrive as photos in a chat and outlive the morning they
    describe — scrolled back to a week later, an undated squad table is
    indistinguishable from today's."""
    from unittest.mock import MagicMock

    from packages.biwenger_tools.api.logic import image_formatter as imf

    ax = MagicMock()
    imf._draw_generated_stamp(ax)

    (x, y, text), kwargs = ax.text.call_args
    assert (x, y) == (1.0, -0.02)  # below the last row, right-aligned
    assert kwargs["ha"] == "right" and kwargs["va"] == "top"
    assert kwargs["color"] == imf._INK_FAINT  # provenance, not data
    assert kwargs["fontsize"] < 9  # smaller than any body cell
    datetime.strptime(text, "%d/%m/%Y %H:%M")  # a real stamp, not a label


def test_extra_columns_widen_the_canvas_instead_of_squeezing_the_others():
    """Column widths are normalised over their total, so every column added
    shrinks all the others. The canvas has to grow by what they weigh, or the
    clause view comes out narrower per column than the plain one — which is
    what made it unreadable when zoomed."""
    from PIL import Image

    rows = [
        {
            "name": f"P{i}",
            "position_id": 2,
            "price": 3_000_000,
            "jp_player": _jp(),
            "Clausulable": "Sí",
            "Cláusula": "5.5M",
        }
        for i in range(15)
    ]
    plain = Image.open(io.BytesIO(build_table_image(rows, "T")))
    clause = Image.open(
        io.BytesIO(build_table_image(rows, "T", extra_cols=["Clausulable", "Cláusula"]))
    )

    plain_per_col = plain.width / 9  # the base column count (JP, Oráculo included)
    clause_per_col = clause.width / 11
    # The extra columns are wider than the base average, so per-column space
    # must not fall — before this it dropped by a third.
    assert clause_per_col >= plain_per_col


def test_the_render_is_dense_enough_to_zoom_into():
    """These are read on a phone by zooming in on one row of fifteen."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    assert imf._DPI >= 200


def test_new_base_columns_do_not_shrink_a_pre_existing_column():
    """`JP` and `Oráculo` are narrower than the base average on purpose, so
    the *mean* px/column necessarily falls even when nothing shrank — that
    is not the property that matters. `Jugador`'s own absolute pixel width
    is: it must not regress from what the pre-existing 7-column table gave.

    467 px is `1435 × (0.28 / 0.86)` — `Jugador`'s share of a real render of
    this exact fixture measured against this file before this change (15
    rows, no extra columns, the 7-column `_BASE_COLUMNS`/9in canvas)."""
    from PIL import Image

    from packages.biwenger_tools.api.logic import image_formatter as imf

    rows = [
        {"name": f"P{i}", "position_id": 2, "price": 3_000_000, "jp_player": _jp()}
        for i in range(15)
    ]
    img = Image.open(io.BytesIO(build_table_image(rows, "T")))

    jugador_weight = next(w for h, w in imf._BASE_COLUMNS if h == "Jugador")
    base_weight = sum(w for _, w in imf._BASE_COLUMNS)
    jugador_px = img.width * jugador_weight / base_weight

    baseline_jugador_px = 1435 * (0.28 / 0.86)
    assert jugador_px >= baseline_jugador_px * 0.98


# --- the three columns: JP, Oráculo, and the blended Proyección ------------


def _row(**overrides):
    row = {
        "name": "Jugador",
        "position_id": 3,
        "price": 1_000_000,
        "jp_player": _jp(),
        "oraculo_matched": False,
        "oraculo_points": None,
        "oraculo_lists": [],
        "custom_prediction": None,
    }
    row.update(overrides)
    return row


def test_an_unmatched_row_renders_an_em_dash_in_the_oraculo_column():
    """No opinion is the normal state for most of a squad most of the week —
    an em-dash says so without reading as a zero score."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    assert imf._oraculo_cell(_row(oraculo_matched=False)) == "—"


def test_a_matched_row_with_no_points_also_renders_an_em_dash():
    """Matching the player is not the same as Oráculo having scored his next
    fixture yet — a still-missing `oraculo_points` is level-1 'no opinion',
    not a zero."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    assert imf._oraculo_cell(_row(oraculo_matched=True, oraculo_points=None)) == "—"


def test_a_zero_projection_is_shown_as_a_real_number():
    """`0.0` is an answer (Oráculo expects him not to play), and must read
    differently from 'no opinion' — see `oraculo_coverage`'s own contract."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    assert imf._oraculo_cell(_row(oraculo_matched=True, oraculo_points=0.0)) == "0.0"


def test_stars_count_qualifying_lists_only():
    """`chollos` ranks value, `capitanes` is derived from the other lists —
    neither is a quality signal, so neither earns a star."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    qualifying = _row(
        oraculo_matched=True,
        oraculo_points=7.4,
        oraculo_lists=["goleadores", "asistentes"],
    )
    non_qualifying = _row(
        oraculo_matched=True,
        oraculo_points=7.4,
        oraculo_lists=["chollos", "capitanes"],
    )
    assert imf._oraculo_cell(qualifying) == "7.4 ★★"
    assert imf._oraculo_cell(non_qualifying) == "7.4"


def test_jp_cell_is_an_em_dash_with_no_jp_data():
    from packages.biwenger_tools.api.logic import image_formatter as imf

    assert imf._jp_cell(None) == "—"
    assert imf._jp_cell(892) == "892"


def test_projection_header_marks_only_when_the_blend_did_not_run():
    """Text first, colour second — the header must say so on its own."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    assert imf._projection_header(blend_ran=True) == "Proyección"
    assert imf._projection_header(blend_ran=False) == "Proyección (JP)"


def test_title_takes_a_suffix_only_when_the_blend_did_not_run():
    from packages.biwenger_tools.api.logic import image_formatter as imf

    assert imf._titled("Mi equipo", blend_ran=True) == "Mi equipo"
    assert imf._titled("Mi equipo", blend_ran=False) == "Mi equipo (solo JP)"


def _jp_with_sf(sf: int) -> dict:
    """A JP player carrying a predicted SF rate, the shape `get_predict_rate`
    reads — distinct from `_jp()` above, which only carries availability."""
    from packages.biwenger_tools.api.player_formatting import SCORE_SF

    return {"predict": [{"type": SCORE_SF, "rate": sf}]}


def test_blended_rows_falls_back_to_jp_when_coverage_is_thin():
    """Level 2 of the design's fallback: below `ORACULO_MIN_COVERAGE`, the
    blend must not run for anybody in the read, even a fully-matched row."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    rows = [
        _row(oraculo_matched=True, oraculo_points=4.0, jp_player=_jp_with_sf(892)),
        _row(oraculo_matched=False, jp_player=_jp_with_sf(300)),
        _row(oraculo_matched=False, jp_player=_jp_with_sf(300)),
        _row(oraculo_matched=False, jp_player=_jp_with_sf(300)),
    ]
    enriched, blend_ran = imf._blended_rows(rows)
    assert blend_ran is False
    assert enriched[0]["custom_prediction"] == 892  # unchanged: JP's own SF


def test_blended_rows_never_recomputes_a_prediction_the_row_already_carries():
    """`custom_prediction` now arrives already computed by the builder from a
    global `k` this function does not have. Recomputing `k` from just the
    rows in front of it — the defect this change closes — would blend the
    first row to a different number than the one the builder committed to."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    rows = [
        _row(
            oraculo_matched=True,
            oraculo_points=4.0,
            jp_player=_jp_with_sf(430),
            custom_prediction=999,
        ),
        _row(oraculo_matched=True, oraculo_points=3.0, jp_player=_jp_with_sf(300)),
        _row(oraculo_matched=True, oraculo_points=5.0, jp_player=_jp_with_sf(500)),
    ]
    enriched, blend_ran = imf._blended_rows(rows)
    assert blend_ran is True
    assert enriched[0]["custom_prediction"] == 999


def test_blended_rows_falls_back_to_jp_when_the_row_carries_no_prediction():
    """Several call sites still build rows with no `oraculo_index`/`k` at all —
    those rows carry no `custom_prediction` key, and must render the plain JP
    rate rather than an em-dash."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    row = _row(jp_player=_jp_with_sf(300))
    del row["custom_prediction"]
    enriched, _ = imf._blended_rows([row])
    assert enriched[0]["custom_prediction"] == 300


def test_blended_rows_never_crashes_on_a_matched_row_with_no_jp_player():
    """A real production shape: Oráculo matched him but the JP name-match
    failed. `custom_prediction` needs a JP number to blend against, so this
    row must come out with no projection rather than raising."""
    from packages.biwenger_tools.api.logic import image_formatter as imf

    rows = [_row(oraculo_matched=True, oraculo_points=4.0, jp_player=None)]
    enriched, _ = imf._blended_rows(rows)
    assert enriched[0]["custom_prediction"] is None


# --- the table sorts and shades by the number it shows ---------------------


def _shown_row(name, jp_sf, custom=None):
    return {
        "name": name,
        "jp_player": {"predict": [{"type": 2, "rate": jp_sf}], "status": "ok"},
        "custom_prediction": custom,
    }


def test_the_table_sorts_by_the_projection_it_displays():
    """The blend moves players past each other. Sorting by the JP rate
    underneath leaves the Proyección column visibly unsorted — Juan Iglesias
    blended to 472 sat below a 437 in the rendered photo."""
    from packages.biwenger_tools.api.player_formatting import sort_key_sf_desc

    rows = [_shown_row("Canales", 461, 437), _shown_row("Iglesias", 430, 472)]
    order = [r["name"] for r in sorted(rows, key=sort_key_sf_desc, reverse=True)]
    assert order == ["Iglesias", "Canales"]


def test_a_row_without_a_blend_sorts_on_its_jp_rate():
    from packages.biwenger_tools.api.player_formatting import sort_key_sf_desc

    rows = [_shown_row("Bajo", 200), _shown_row("Alto", 600)]
    order = [r["name"] for r in sorted(rows, key=sort_key_sf_desc, reverse=True)]
    assert order == ["Alto", "Bajo"]


def test_the_colour_band_follows_the_blended_number():
    """A player the blend lifts across a threshold must be shaded for where he
    landed, not where JP left him."""
    from packages.biwenger_tools.api.player_formatting import (
        band_for_score,
        shown_score,
    )

    lifted = _shown_row("Dmitrovic", 404, 461)
    assert band_for_score(shown_score(lifted)) == band_for_score(461)


def test_shown_score_is_none_when_there_is_no_projection_at_all():
    from packages.biwenger_tools.api.player_formatting import shown_score

    assert shown_score({"name": "X", "jp_player": None}) is None
