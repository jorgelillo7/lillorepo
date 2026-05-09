"""Generates PNG table images for Telegram using matplotlib."""

import io

import matplotlib

matplotlib.use("Agg")  # non-interactive backend, must be set before pyplot import
import matplotlib.pyplot as plt  # noqa: E402

from core.sdk.jp import get_predict_rate  # noqa: E402
from packages.biwenger_tools.teams_analyzer.telegram_formatter import (  # noqa: E402
    _count_status,
    _juega_str,
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

_GREEN = "#388e3c"
_AMBER = "#f57f17"
_RED = "#c62828"

_BASE_COLS = ["Jugador", "Pos", "Precio", "SF", "Racha", "Juega"]
_COL_WIDTHS = [0.30, 0.07, 0.09, 0.07, 0.08, 0.14]


def _strip_emoji(text: str) -> str:
    """Remove characters outside the Basic Multilingual Plane (emoji, etc.)."""
    return "".join(c for c in text if ord(c) <= 0xFFFF).strip()


def _price_exact(price) -> str:
    """Show price with one decimal place (e.g. 24.5M) instead of rounding."""
    if not price:
        return "0"
    m = int(price) / 1_000_000
    return f"{m:.1f}M" if price % 1_000_000 else f"{int(m)}M"


def _pos_str(row: dict) -> str:
    """Primary position + alt positions, e.g. 'DEF/MED'."""
    primary = _short_pos(row.get("position_id"))
    alts = row.get("alt_positions") or []
    if alts:
        return "/".join([primary] + [_short_pos(a) for a in alts[:2]])
    return primary


def _row_data(row: dict, extra_cols: list[str]) -> list[str]:
    jp = row.get("jp_player")
    sf = get_predict_rate(jp, SCORE_SF) if jp else None
    cells = [
        _strip_emoji(row.get("name", ""))[:22],
        _pos_str(row),
        _price_exact(row.get("price", 0)),
        str(sf) if sf is not None else "-",
        str(jp.get("streak", 0)) if jp else "-",
        _juega_str(jp),
    ]
    for col in extra_cols:
        cells.append(str(row.get(col, "")))
    return cells


def _draw_status_summary(ax, g: int, y: int, r: int, n: int) -> None:
    """Draws a colored-dot status summary line below the title."""
    parts = [
        (f"  {n} jugadores  ", "#555555"),
        ("  ●  ", _GREEN),
        (f"{g} ok  ", "#333333"),
        ("  ●  ", _AMBER),
        (f"{y} alerta  ", "#333333"),
        ("  ●  ", _RED),
        (f"{r} baja  ", "#333333"),
    ]
    x = 0.02
    for text, color in parts:
        ax.text(
            x,
            0.935,
            text,
            transform=ax.transAxes,
            fontsize=9,
            ha="left",
            va="top",
            color=color,
        )
        x += len(text) * 0.012


def build_table_image(
    rows: list[dict],
    title: str,
    extra_cols: list[str] | None = None,
) -> bytes:
    """Returns PNG bytes of a styled player table."""
    extra_cols = extra_cols or []
    headers = _BASE_COLS + extra_cols

    sorted_rows = sorted(rows, key=_sort_key_sf_desc, reverse=True)
    g, ylw, r, _ = _count_status(sorted_rows)

    cell_data = [_row_data(row, extra_cols) for row in sorted_rows]
    cell_colors = [
        [_ROW_BG.get(_status_emoji(row.get("jp_player")), _ROW_BG["⚪"])] * len(headers)
        for row in sorted_rows
    ]

    n_rows = len(cell_data)
    n_cols = len(headers)
    extra_width = 0.18 * len(extra_cols)
    fig_w = 11 + extra_width
    fig_h = max(2.5, 0.38 * n_rows + 1.8)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.axis("off")

    ax.text(
        0.5,
        0.995,
        _strip_emoji(title),
        transform=ax.transAxes,
        fontsize=14,
        fontweight="bold",
        ha="center",
        va="top",
        color=_TITLE_FG,
    )
    _draw_status_summary(ax, g, ylw, r, len(sorted_rows))

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
