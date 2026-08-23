"""Generates PNG table images for Telegram using matplotlib."""

import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # non-interactive backend, must be set before pyplot import
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.offsetbox import (  # noqa: E402
    AnchoredOffsetbox,
    HPacker,
    TextArea,
    VPacker,
)

from core.constants import MADRID_TZ  # noqa: E402
from core.sdk.jp import get_predict_rate  # noqa: E402
from packages.biwenger_tools.api.player_formatting import (  # noqa: E402
    SCORE_SF,
    availability,
    count_availability,
    count_bands,
    count_bench,
    is_bench,
    play_status_label,
    sf_band,
    short_position,
    sort_key_sf_desc,
)

# Three colour jobs, and only three. Dark surface: the table is read on a
# phone, in Telegram, which is dark for most of the day.
#
# Availability is a *status*: reserved hues, never reused for anything else, and
# never carrying meaning alone — the reason is spelled out beside it.
#
# Not being a certain starter is the third job — left out of the projected
# eleven, or listed as a doubt — and it is a state rather than a quantity or an
# injury. It gets amber, its own reserved hue: such a player is available (so
# he is not red) and his projection is whatever it is (so he is not a step on
# the violet ramp). Amber measures normal-vision
# ΔE 15.6 against the reserved red — the pair a reader must never confuse,
# because "no juega" and "sale del banquillo" are different news.
#
# The projection is *magnitude*, so it is one hue stepped dark→light. Light is
# the high end here: on a dark surface, brightness is what reads as "more". It
# used to be green/amber/grey, which is a rainbow for a quantity: three hues
# imply three kinds, not three amounts.
#
# Violet, not the more obvious green: green sits ΔE 4.1 from the reserved red
# under deuteranopia, and both appear in this same table — a reader with the
# commonest colour blindness could not tell "projects well" from "does not
# play". The ramp is monotone in lightness (relative luminance 0.12 → 0.19 →
# 0.33 → 0.56), a single hue, and every step clears 3:1 on the surface. The
# status trio clears the normal-vision floor as a set; the green↔red pair sits
# in the CVD floor band, which is legal here precisely because neither ever
# appears without its word beside it.
_SURFACE = "#101317"
_INK = "#eef0f6"
_INK_SOFT = "#a8adbd"
_INK_FAINT = "#7c8194"

# Row tints are the faintest legible step off the surface: the row's job is to
# group, and anything stronger competes with the data for the reader's eye.
_ROW_BG = {
    "plays": "#161a20",
    "out": "#241519",
    "unknown": "#15171c",
}
_BENCH_BG = "#231d15"
_CRITICAL = "#ff6b6b"
_GOOD = "#3ddc84"
_BENCH = "#f0a63a"

# Projected score, low -> high.
_BAND_FG = {
    "low": "#7b6ad2",
    "mid": "#a08cf5",
    "high": "#cbbcff",
    "none": "#5f6070",
}

# Chrome stays neutral so a hue never means "header" and "high projection" at
# once — a colour that labels furniture cannot also label data.
_HEADER_BG = "#1e2430"
_HEADER_FG = "#eef0f6"
_TITLE_FG = "#cbbcff"
_EDGE = "#252a33"
# The marker for a player with nothing to report. Deliberately near the
# surface: eleven of these in a column of fifteen, and anything more legible
# competes with the three that are the reason the column exists.
_MARK_QUIET = "#3c4354"

# The bench marker. A filled circle starts, a hollow one comes on later — the
# shape carries it, so the amber is reinforcement rather than the only signal.
# Both are BMP glyphs: `_strip_emoji` exists because matplotlib draws a
# dotted-circle placeholder for anything above it, and a 🪑 would land there.
_MARK_STARTS = "●"
_MARK_BENCH = "○"
_MARK_OUT = "\u2715"

# Base columns: (header, relative_width). Keep header and width together so
# adding/removing a column is a single-line edit instead of two parallel lists.
_BASE_COLUMNS: list[tuple[str, float]] = [
    ("", 0.03),
    ("Jugador", 0.28),
    ("Pos", 0.07),
    ("Precio", 0.09),
    ("Proyección", 0.15),
    ("Racha", 0.08),
    ("Juega", 0.16),
]
_EXTRA_COL_WIDTH = 0.18

# Canvas width for a table with no extra columns; the clause views scale up
# from it in proportion to what they add.
_BASE_FIG_WIDTH_IN = 9

# These are read on a phone, and read by zooming in — the row you care about
# is one of fifteen at six-point type. 200 dpi over the old 150 is a third
# more pixels on each axis for a file still well inside Telegram's limit
# (the widest table here lands around 300 KB against a 10 MB cap).
_DPI = 200


# Modifiers that only exist to decorate an adjacent emoji: variation
# selectors, the zero-width joiner and the combining keycap. They sit inside
# the BMP, so dropping only the astral plane leaves them orphaned — and an
# orphaned modifier is what matplotlib draws as a dotted-circle placeholder.
_EMOJI_MODIFIERS = frozenset([0x200D, 0x20E3] + list(range(0xFE00, 0xFE10)))


def _strip_emoji(text: str) -> str:
    """Remove emoji and anything left behind that only decorated one.

    `🛡️` is two codepoints — the shield above the BMP plus U+FE0F. Removing
    the shield alone left the selector standing, which is why the squad image
    carried a stray glyph where its icon should have been.
    """
    return "".join(
        c for c in text if ord(c) <= 0xFFFF and ord(c) not in _EMOJI_MODIFIERS
    ).strip()


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


def _mark(jp_player: dict | None) -> str:
    """The marker glyph: he starts, he comes on, or he is not there at all.

    Availability wins over the bench: an injured substitute is out, and two
    marks for one player is how a reader stops trusting the column.
    """
    if availability(jp_player) == "out":
        return _MARK_OUT
    return _MARK_BENCH if is_bench(jp_player) else _MARK_STARTS


def _row_bg(jp_player: dict | None) -> str:
    """The row tint. Availability first — an injured substitute is out, and
    saying "banquillo" about him would bury the news that matters."""
    state = availability(jp_player)
    if state == "plays" and is_bench(jp_player):
        return _BENCH_BG
    return _ROW_BG[state]


def _row_data(row: dict, extra_cols: list[str]) -> list[str]:
    jp = row.get("jp_player")
    sf = get_predict_rate(jp, SCORE_SF) if jp else None
    cells = [
        _mark(jp),
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


def total_value(rows: list[dict]) -> str:
    """The squad's worth: every row's cf-base price, formatted like the column.

    Squads only. The market table's rows are other people's players, so
    summing them would answer a question nobody asked.
    """
    return _price_exact(sum(r.get("price") or 0 for r in rows))


def _draw_status_summary(ax, rows: list[dict], show_total_value: bool) -> None:
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
    bench = count_bench(rows)
    if bench:
        # Inside "juegan", not beside it: a substitute or a doubt is fit and
        # available, and moving either out of that count would contradict the
        # row colour.
        first += [(_MARK_BENCH, _BENCH), (f"{bench} no salen de inicio", _INK)]
    if show_total_value:
        first += [
            ("\u00b7", _INK_FAINT),
            ("valor", _INK_SOFT),
            (total_value(rows), _INK),
        ]
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


def _draw_generated_stamp(ax) -> None:
    """When this picture was made, in the corner where nothing else lives.

    Bottom right, under the last row and right-aligned: the table grows
    downward and its rightmost column is the shortest text on the row, so
    that corner is the one place a line can go without displacing anything.
    Muted ink and small type — it is provenance, and provenance that competes
    with the data has been put in the wrong place.

    Worth having at all because these arrive as photos in a chat and outlive
    the morning they describe: scrolled back to a week later, a squad table
    with no date is indistinguishable from today's.
    """
    ax.text(
        1.0,
        -0.02,
        datetime.now(MADRID_TZ).strftime("%d/%m/%Y %H:%M"),
        transform=ax.transAxes,
        fontsize=7,
        ha="right",
        va="top",
        color=_INK_FAINT,
    )


def build_table_image(
    rows: list[dict],
    title: str,
    extra_cols: list[str] | None = None,
    show_total_value: bool = False,
) -> bytes:
    """Returns PNG bytes of a styled player table.

    `show_total_value` adds the summed cf-base price of the rows to the
    header. Off by default because the same renderer draws the market, where
    the total would be the price of other people's players.
    """
    extra_cols = extra_cols or []
    base_headers = [h for h, _ in _BASE_COLUMNS]
    base_widths = [w for _, w in _BASE_COLUMNS]
    headers = base_headers + extra_cols

    sorted_rows = sorted(rows, key=sort_key_sf_desc, reverse=True)
    cell_data = [_row_data(row, extra_cols) for row in sorted_rows]
    cell_colors = [
        [_row_bg(row.get("jp_player"))] * len(headers) for row in sorted_rows
    ]

    n_rows = len(cell_data)
    n_cols = len(headers)
    # Widen the figure by exactly what the extra columns weigh.
    #
    # Column widths are normalised over their total, so every column added
    # shrinks all the others. The figure used to grow a flat 0.2 in per extra
    # column, which nowhere near covered it: the clause view carries two
    # extras worth 0.36 against the base's 0.86, so the base columns lost 30%
    # of their width while the canvas gained 4%. A fifteen-player squad came
    # out 1122 px wide — narrower per column than the seven-column view — and
    # unreadable as soon as anyone zoomed in.
    base_weight = sum(base_widths)
    total_weight = base_weight + _EXTRA_COL_WIDTH * len(extra_cols)
    fig_w = _BASE_FIG_WIDTH_IN * total_weight / base_weight
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
    _draw_status_summary(ax, sorted_rows, show_total_value)

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

        mark_col = 0
        name_col = base_headers.index("Jugador")
        sf_col = base_headers.index("Proyección")
        plays_col = base_headers.index("Juega")
        # Squad size is a per-league setting, commonly up to 25, so that is the
        # density this has to stay legible at. Below ~18 rows the figure still
        # grows; past that it is capped, so the type gives back the room.
        body_size = 9.5 if n_rows <= 18 else 8.5
        for i in range(1, n_rows + 1):
            jp = sorted_rows[i - 1].get("jp_player")
            for j in range(n_cols):
                cell = table[i, j]
                cell.get_text().set_fontsize(body_size)
                cell.set_edgecolor(_EDGE)
                # Every cell gets an explicit ink. matplotlib's default is
                # black, which was invisible on the dark surface for the four
                # columns nothing else recolours (Pos, Precio, Racha, Juega).
                cell.get_text().set_color(_INK_SOFT)
            # Three independent signals, three independent colours.
            table[i, sf_col].get_text().set_color(_BAND_FG[sf_band(jp)])
            table[i, name_col].get_text().set_color(_INK)
            table[i, mark_col].get_text().set_color(_MARK_QUIET)
            if is_bench(jp):
                # Marker, name and reason together: one glance down the
                # marker column finds every substitute, and the reader who
                # stops on the row gets the word rather than a colour to
                # decode.
                table[i, mark_col].get_text().set_color(_BENCH)
                table[i, name_col].get_text().set_color(_BENCH)
                bench_cell = table[i, plays_col].get_text()
                bench_cell.set_color(_BENCH)
                bench_cell.set_fontweight("bold")
            if availability(jp) == "out":
                table[i, mark_col].get_text().set_color(_CRITICAL)
                out_cell = table[i, plays_col].get_text()
                out_cell.set_color(_CRITICAL)
                out_cell.set_fontweight("bold")

        for j, width in enumerate(col_widths):
            for i in range(n_rows + 1):
                table[i, j].set_width(width)

    _draw_generated_stamp(ax)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, bbox_inches="tight", facecolor=_SURFACE)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
