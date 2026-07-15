"""Unit tests for `api/logic/image_formatter.build_table_image`."""

from packages.biwenger_tools.api.logic.image_formatter import build_table_image

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
