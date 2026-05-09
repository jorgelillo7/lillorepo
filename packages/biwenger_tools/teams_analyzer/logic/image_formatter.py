"""Generates PNG table images for Telegram using matplotlib."""

import io

import matplotlib

matplotlib.use("Agg")  # non-interactive backend, must be set before pyplot import
import matplotlib.pyplot as plt  # noqa: E402

from core.sdk.jp import get_predict_rate  # noqa: E402
from packages.biwenger_tools.teams_analyzer.telegram_formatter import (  # noqa: E402
    _count_status,
    _juega_str,
    _price_millions,
    _short_pos,
    _sort_key_sf_desc,
    _status_emoji,
)

SCORE_SF = 2

_ROW_BG = {
    "🟢": "#e8f5e9",
    "🟡": "#fffde7",
    "🔴": "#ffebee",
    "⚪": "#f5f5f5",
}

_HEADER_BG = "#1a237e"
_HEADER_FG = "white"
_TITLE_FG = "#1a237e"
_EDGE = "#e0e0e0"

_BASE_COLS = ["Jugador", "Pos", "Precio", "SF", "Racha", "Juega"]
_COL_WIDTHS = [0.30, 0.07, 0.09, 0.07, 0.08, 0.14]


def _row_data(row: dict, extra_cols: list[str]) -> list[str]:
    jp = row.get("jp_player")
    sf = get_predict_rate(jp, SCORE_SF) if jp else None
    cells = [
        row.get("name", "")[:22],
        _short_pos(row.get("position_id")),
        _price_millions(row.get("price", 0)),
        str(sf) if sf is not None else "—",
        str(jp.get("streak", 0)) if jp else "—",
        _juega_str(jp),
    ]
    for col in extra_cols:
        cells.append(str(row.get(col, "")))
    return cells


def build_table_image(
    rows: list[dict],
    title: str,
    extra_cols: list[str] | None = None,
) -> bytes:
    """Returns PNG bytes of a styled player table."""
    extra_cols = extra_cols or []
    headers = _BASE_COLS + extra_cols

    sorted_rows = sorted(rows, key=_sort_key_sf_desc, reverse=True)
    g, y, r, _ = _count_status(sorted_rows)

    cell_data = [_row_data(row, extra_cols) for row in sorted_rows]
    cell_colors = [
        [_ROW_BG.get(_status_emoji(row.get("jp_player")), _ROW_BG["⚪"])] * len(headers)
        for row in sorted_rows
    ]

    n_rows = len(cell_data)
    n_cols = len(headers)
    extra_width = 0.18 * len(extra_cols)
    fig_w = 11 + extra_width
    fig_h = max(2.5, 0.38 * n_rows + 1.6)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.axis("off")

    summary = f"{len(sorted_rows)} jug.  ·  🟢 {g}  🟡 {y}  🔴 {r}"
    ax.text(
        0.5,
        0.99,
        title,
        transform=ax.transAxes,
        fontsize=14,
        fontweight="bold",
        ha="center",
        va="top",
        color=_TITLE_FG,
    )
    ax.text(
        0.5,
        0.93,
        summary,
        transform=ax.transAxes,
        fontsize=10,
        ha="center",
        va="top",
        color="#555555",
    )

    col_widths = _COL_WIDTHS + [0.18] * len(extra_cols)
    total = sum(col_widths)
    col_widths = [w / total for w in col_widths]

    table = ax.table(
        cellText=cell_data,
        colLabels=headers,
        cellColours=cell_colors,
        cellLoc="left",
        loc="center",
        bbox=[0, 0, 1, 0.88],
    )

    for j in range(n_cols):
        cell = table[0, j]
        cell.set_facecolor(_HEADER_BG)
        cell.get_text().set_color(_HEADER_FG)
        cell.get_text().set_fontweight("bold")
        cell.get_text().set_fontsize(9)
        cell.set_edgecolor(_EDGE)

    for i in range(1, n_rows + 1):
        for j in range(n_cols):
            cell = table[i, j]
            cell.get_text().set_fontsize(8.5)
            cell.set_edgecolor(_EDGE)

    for j, width in enumerate(col_widths):
        for i in range(n_rows + 1):
            table[i, j].set_width(width)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
