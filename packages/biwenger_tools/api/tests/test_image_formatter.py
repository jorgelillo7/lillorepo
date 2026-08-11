"""Unit tests for `api/logic/image_formatter.build_table_image`."""

from packages.biwenger_tools.api.logic.image_formatter import (
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
