"""Generates PNG table images for Telegram using matplotlib."""

import io

import matplotlib

matplotlib.use("Agg")  # non-interactive backend, must be set before pyplot import
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.offsetbox import (  # noqa: E402
    AnchoredOffsetbox,
    HPacker,
    TextArea,
    VPacker,
)

from core.sdk.jp import get_predict_rate  # noqa: E402
from packages.biwenger_tools.api.player_formatting import (  # noqa: E402
    SCORE_SF,
    availability,
    count_availability,
    count_bands,
    play_status_label,
    sf_band,
    short_position,
    sort_key_sf_desc,
)

# Two colour jobs, and only two.
#
# Availability is a *status*: reserved hues, never reused for anything else, and
# never carrying meaning alone — the reason is spelled out beside it.
#
# The projection is *magnitude*, so it is one hue stepped light→dark. It used to
# be green/amber/grey, which is a rainbow for a quantity: three hues imply three
# kinds, not three amounts. The bar length carries the value and the number sits
# beside it, so the lightest step needs no contrast of its own.
#
# Violet, not the more obvious green: green sits ΔE 4.1 from the reserved red
# under deuteranopia, and both appear in this same table — a reader with the
# commonest colour blindness could not tell "projects well" from "does not
# play". Violet measures 21.6 against it. Ramp verified with the ordinal
# validator: monotone lightness, adjacent dL >= 0.06, single hue (8 degrees).
_SURFACE = "#fcfcfb"
_INK = "#0b0b0b"
_INK_SOFT = "#52514e"
_INK_FAINT = "#8b8a85"

_ROW_BG = {
    "plays": _SURFACE,
    "out": "#fdeceb",
    "unknown": "#f4f3f0",
}
_CRITICAL = "#d03b3b"
_GOOD = "#0ca30c"

# Projected score, low -> high.
_BAND_FG = {
    "low": "#a89fe6",
    "mid": "#6f5fe3",
    "high": "#3b3193",
    "none": "#c8c7c2",
}

# Chrome stays neutral so blue never means "header" and "high projection" at
# once — a colour that labels furniture cannot also label data.
_HEADER_BG = "#2b2456"
_HEADER_FG = "#fcfcfb"
_TITLE_FG = "#3b3193"
_EDGE = "#e7e5e0"

# Base columns: (header, relative_width). Keep header and width together so
# adding/removing a column is a single-line edit instead of two parallel lists.
_BASE_COLUMNS: list[tuple[str, float]] = [
    ("Jugador", 0.30),
    ("Pos", 0.07),
    ("Precio", 0.09),
    ("Proyección", 0.15),
    ("Racha", 0.08),
    ("Juega", 0.16),
]
_EXTRA_COL_WIDTH = 0.18


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
    primary = short_position(row.get("position_id"))
    alts = row.get("alt_positions") or []
    if alts:
        return "/".join([primary] + [short_position(a) for a in alts[:2]])
    return primary


# Five blocks of projected score, so the eye ranks players without reading a
# number. The thresholds are the same ones `sf_band` uses.
_BAR_MAX = 500


def _sf_bar(sf) -> str:
    """`▮▮▮▯▯ 328` — the projection as a shape first and a number second."""
    if sf is None:
        return "—"
    filled = max(1, min(5, round(sf / _BAR_MAX * 5)))
    return "\u25ae" * filled + "\u25af" * (5 - filled) + f" {sf}"


def _row_data(row: dict, extra_cols: list[str]) -> list[str]:
    jp = row.get("jp_player")
    sf = get_predict_rate(jp, SCORE_SF) if jp else None
    cells = [
        _strip_emoji(row.get("name", ""))[:22],
        _pos_str(row),
        _price_exact(row.get("price", 0)),
        _sf_bar(sf),
        str(jp.get("streak", 0)) if jp else "-",
        play_status_label(jp),
    ]
    for col in extra_cols:
        cells.append(str(row.get(col, "")))
    return cells


def _row_of(parts: list[tuple[str, str]]) -> HPacker:
    """One legend line. `HPacker` measures each run and spaces them for real —
    the previous version advanced x by character count, which drifted as soon
    as the figure widened for extra columns and collided with the table."""
    return HPacker(
        children=[
            TextArea(text, textprops={"color": color, "fontsize": 9})
            for text, color in parts
        ],
        pad=0,
        sep=6,
        align="baseline",
    )


def _draw_status_summary(ax, rows: list[dict]) -> None:
    """Two lines because there are two questions, and one line answering both
    is what made a fit starter with a modest forecast read like an injury.

    Who can play, then how the ones who play are projected.
    """
    plays, out, unknown = count_availability(rows)
    first = [
        (f"{len(rows)} jugadores", _INK_SOFT),
        ("\u25cf", _GOOD),
        (f"{plays} juegan", _INK),
    ]
    if out:
        first += [("\u25cf", _CRITICAL), (f"{out} no juegan", _INK)]
    if unknown:
        first += [("\u25cf", _INK_FAINT), (f"{unknown} sin datos", _INK)]
    lines = [_row_of(first)]

    high, mid, low = count_bands(rows)
    if high or mid or low:
        lines.append(
            _row_of(
                [
                    ("de los que juegan:", _INK_SOFT),
                    (f"\u25ae\u25ae\u25ae {high} alto", _BAND_FG["high"]),
                    (f"\u25ae\u25ae {mid} medio", _BAND_FG["mid"]),
                    (f"\u25ae {low} bajo", _INK_FAINT),
                ]
            )
        )
    box = AnchoredOffsetbox(
        loc="upper left",
        child=VPacker(children=lines, pad=0, sep=3, align="left"),
        bbox_to_anchor=(0.0, 0.955),
        bbox_transform=ax.transAxes,
        frameon=False,
        borderpad=0,
        pad=0,
    )
    ax.add_artist(box)


def build_table_image(
    rows: list[dict],
    title: str,
    extra_cols: list[str] | None = None,
) -> bytes:
    """Returns PNG bytes of a styled player table."""
    extra_cols = extra_cols or []
    base_headers = [h for h, _ in _BASE_COLUMNS]
    base_widths = [w for _, w in _BASE_COLUMNS]
    headers = base_headers + extra_cols

    sorted_rows = sorted(rows, key=sort_key_sf_desc, reverse=True)
    cell_data = [_row_data(row, extra_cols) for row in sorted_rows]
    cell_colors = [
        [_ROW_BG[availability(row.get("jp_player"))]] * len(headers)
        for row in sorted_rows
    ]

    n_rows = len(cell_data)
    n_cols = len(headers)
    extra_width = 0.20 * len(extra_cols)
    fig_w = 9 + extra_width
    # Slow height growth so all images stay in the ~750–975 px range at 150 dpi.
    # This keeps Telegram's display-scale consistent across small and large squads.
    fig_h = min(6.5, max(3.5, 4.5 + 0.06 * n_rows))
    # Title plus two legend lines need a fixed number of inches, not a fixed
    # fraction: the figure is 3.5in tall for three players and 6.5in for
    # thirty, so a constant fraction let the table climb into the legend.
    _HEADROOM_IN = 1.05
    table_top = 1 - _HEADROOM_IN / fig_h

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)
    ax.axis("off")

    ax.text(
        0.5,
        1.0,
        _strip_emoji(title),
        transform=ax.transAxes,
        fontsize=14,
        fontweight="bold",
        ha="center",
        va="top",
        color=_TITLE_FG,
    )
    _draw_status_summary(ax, sorted_rows)

    col_widths = base_widths + [_EXTRA_COL_WIDTH] * len(extra_cols)
    total = sum(col_widths)
    col_widths = [w / total for w in col_widths]

    if not cell_data:
        # matplotlib's ax.table raises IndexError on an empty cellText, so
        # an empty squad/market renders a placeholder instead of a table.
        ax.text(
            0.5,
            0.45,
            "Sin jugadores",
            transform=ax.transAxes,
            fontsize=12,
            ha="center",
            va="center",
            color=_INK_SOFT,
        )
    else:
        table = ax.table(
            cellText=cell_data,
            colLabels=headers,
            cellColours=cell_colors,
            cellLoc="left",
            loc="center",
            bbox=[0, 0, 1, table_top],
        )

        for j in range(n_cols):
            cell = table[0, j]
            cell.set_facecolor(_HEADER_BG)
            cell.get_text().set_color(_HEADER_FG)
            cell.get_text().set_fontweight("bold")
            cell.get_text().set_fontsize(10)
            cell.set_edgecolor(_EDGE)

        sf_col = base_headers.index("Proyección")
        plays_col = base_headers.index("Juega")
        # A full Biwenger squad is 25 players, so that is the density this has
        # to stay legible at — not a hypothetical. Below ~18 rows the figure
        # still grows; past that it is capped, so the type gives back the room.
        body_size = 9.5 if n_rows <= 18 else 8.5
        for i in range(1, n_rows + 1):
            jp = sorted_rows[i - 1].get("jp_player")
            for j in range(n_cols):
                cell = table[i, j]
                cell.get_text().set_fontsize(body_size)
                cell.set_edgecolor(_EDGE)
            # Two independent signals, two independent colours.
            table[i, sf_col].get_text().set_color(_BAND_FG[sf_band(jp)])
            table[i, 0].get_text().set_color(_INK)
            if availability(jp) == "out":
                out_cell = table[i, plays_col].get_text()
                out_cell.set_color(_CRITICAL)
                out_cell.set_fontweight("bold")

        for j, width in enumerate(col_widths):
            for i in range(n_rows + 1):
                table[i, j].set_width(width)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=_SURFACE)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
