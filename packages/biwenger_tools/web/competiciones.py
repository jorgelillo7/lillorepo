"""Reading the league's competitions workbook.

Pure functions: no I/O, no Flask. The route fetches every tab of every
workbook a season has and hands the raw cell rows in here.

**The sheet describes itself.** A tab is classified by its own shape, not by a
name held in config:

- the H2H tab carries a ``Jornada | Partido | …`` header row — see `h2h.py`,
  which owns everything about that competition;
- a table tab starts with ``Nombre de la liga`` in A1, the format the league
  has used since the awards pages existed;
- anything else is reported, never silently dropped.

So adding a competition is adding a tab. No config entry, no secret, no
deploy — which is the whole point, because a sheet id per competition per
season is what left the awards pages empty for a year.
"""

from dataclasses import dataclass, field

# Row 1 label that marks a tab as a table competition, and the rows the
# format reserves before the data starts:
#   1 Nombre de la liga | <name>
#   2 Descripción       | <text>
#   3 Premio            | <text>
#   4 (blank)
#   5 <header row>
#   6+ data
_TABLE_MARKER = "nombre de la liga"
_HEADER_ROW = 4
_FIRST_DATA_ROW = 5

# The H2H fixture block is found by its header, wherever the owner put it.
_H2H_HEADER = ("jornada", "partido")


@dataclass
class Section:
    """One sub-table inside a tab.

    Group stages put several in one tab — the 25-26 Copa Santa Claus has
    ``GRUPO A`` and ``GRUPO B`` stacked with a header row each. Reading only
    the first header, as the old reader did, rendered the second group's
    header as if it were a team.
    """

    titulo: str
    headers: list[str]
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class Competition:
    """A table competition: its blurb and one or more sections."""

    key: str
    label: str
    nombre: str
    descripcion: str
    premio: str
    sections: list[Section] = field(default_factory=list)


def _cell(row: list[str], index: int) -> str:
    """A cell of a ragged row — the API truncates at the last non-empty one."""
    return (row[index] or "").strip() if index < len(row) else ""


def _slug(title: str) -> str:
    """A DOM-safe tab id. Collisions are impossible: tab titles are unique
    within a workbook, and the season prefix keeps workbooks apart."""
    out = [c.lower() if c.isalnum() else "-" for c in title]
    return "".join(out).strip("-") or "tab"


def is_h2h_tab(rows: list[list[str]]) -> bool:
    """True when a tab carries the H2H fixture header."""
    return any(
        tuple(_cell(row, i).lower() for i in (0, 1)) == _H2H_HEADER for row in rows[:10]
    )


def is_table_tab(rows: list[list[str]]) -> bool:
    """True when a tab follows the `Nombre de la liga` awards format."""
    return bool(rows) and _cell(rows[0], 0).lower() == _TABLE_MARKER


def split_sections(header: list[str], body: list[list[str]]) -> list[Section]:
    """Split a tab's data into sections, one per repeated header row.

    A row that repeats the header's labels from column B onward opens a new
    section, and its column A is that section's title. Exact rule, no
    heuristics — a group stage writes the same header again, and nothing else
    in these sheets does.

    A tab with a single section gets an empty title and keeps column A's
    label as a normal header (``Equipo``, ``Record``…).
    """
    labels = [c.strip() for c in header[1:]]
    sections = [Section(titulo=header[0].strip(), headers=list(header))]

    for row in body:
        if labels and [c.strip() for c in row[1:]] == labels:
            sections.append(Section(titulo=_cell(row, 0), headers=list(row)))
            continue
        if any(c.strip() for c in row):
            sections[-1].rows.append(list(row))

    if len(sections) == 1:
        sections[0].titulo = ""
    else:
        # With several groups, column A holds the group name rather than a
        # column label, so it has none to show.
        for section in sections:
            section.headers = [""] + list(section.headers[1:])

    return [s for s in sections if s.rows]


def parse_table_tab(title: str, rows: list[list[str]]) -> Competition | None:
    """A table tab as a `Competition`, or None when it holds no data.

    Returning None for an empty tab is deliberate and different from dropping
    a short one silently: the caller reports what it skipped.
    """
    if len(rows) <= _FIRST_DATA_ROW:
        return None
    header = rows[_HEADER_ROW]
    if not any(c.strip() for c in header):
        return None

    nombre = _cell(rows[0], 1) or title
    sections = split_sections(header, rows[_FIRST_DATA_ROW:])
    if not sections:
        return None

    return Competition(
        key=_slug(title),
        label=nombre,
        nombre=nombre,
        descripcion=_cell(rows[1], 1),
        premio=_cell(rows[2], 1),
        sections=sections,
    )


def read_workbooks(
    workbooks: list[list[tuple[str, list[list[str]]]]],
) -> tuple[list[list[str]], list[Competition], list[str]]:
    """Classify every tab of every workbook a season has.

    Returns the H2H fixture rows (empty when the season has no H2H tab), the
    table competitions in the order the owner arranged them, and the tabs that
    were skipped with the reason. Nothing disappears without being named — the
    old reader dropped any tab under six rows in silence, so a half-written
    competition looked identical to one that did not exist.
    """
    h2h_rows: list[list[str]] = []
    competitions: list[Competition] = []
    skipped: list[str] = []

    for workbook in workbooks:
        for title, rows in workbook:
            if is_h2h_tab(rows):
                if h2h_rows:
                    skipped.append(f"«{title}»: ya hay otra pestaña de H2H, se ignora")
                else:
                    h2h_rows = rows
                continue
            if not is_table_tab(rows):
                skipped.append(
                    f"«{title}»: no empieza por «Nombre de la liga» ni es un "
                    "calendario H2H, se ignora"
                )
                continue
            competition = parse_table_tab(title, rows)
            if competition is None:
                skipped.append(f"«{title}»: sin filas de datos todavía")
                continue
            competitions.append(competition)

    return h2h_rows, competitions, skipped
