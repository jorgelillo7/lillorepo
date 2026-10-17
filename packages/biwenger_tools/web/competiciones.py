"""Reading the league's competitions workbook.

Pure functions: no I/O, no Flask. The route fetches every tab of every
workbook a season has and hands the raw cell rows in here.

**The sheet describes itself.** A tab is classified by its own shape, not by a
name held in config:

- the H2H tab carries a ``Jornada | Partido | …`` header row — see `h2h.py`,
  which owns everything about that competition;
- a table tab starts with ``Nombre de la liga`` in A1, the format the league
  has used since the awards pages existed;
- a group stage's fixture list carries a ``Jornada | Grupo | …`` header row;
  it joins the table tab right before it in the same workbook — the
  standings it feeds — or stands alone when there is none;
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
# So is a group stage's fixture list (the 26-27 Copa Santa Claus).
_FIXTURE_HEADER = ("jornada", "grupo")


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
class Match:
    """One fixture of a group stage. Points stay as the sheet wrote them."""

    grupo: str
    home: str
    home_points: str
    away_points: str
    away: str

    @property
    def played(self) -> bool:
        return bool(self.home_points and self.away_points)

    @property
    def outcome(self) -> str:
        """``home``, ``away``, ``draw``, or empty while unplayed."""
        if not self.played:
            return ""
        try:
            home, away = (
                float(p.replace(",", ".")) for p in (self.home_points, self.away_points)
            )
        except ValueError:
            return ""
        return "home" if home > away else "away" if away > home else "draw"


@dataclass
class FixtureRound:
    """A jornada's matches; `open` marks the ones shown unfolded."""

    jornada: str
    matches: list[Match] = field(default_factory=list)
    open: bool = False

    @property
    def played(self) -> bool:
        return all(m.played for m in self.matches)

    @property
    def started(self) -> bool:
        return any(m.played for m in self.matches)


@dataclass
class Competition:
    """A table competition: its blurb, its sections and, for a group stage,
    its fixtures."""

    key: str
    label: str
    nombre: str
    descripcion: str
    premio: str
    sections: list[Section] = field(default_factory=list)
    rounds: list[FixtureRound] = field(default_factory=list)


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


def _fixture_header_at(rows: list[list[str]]) -> int | None:
    for i, row in enumerate(rows[:10]):
        if tuple(_cell(row, c).lower() for c in (0, 1)) == _FIXTURE_HEADER:
            return i
    return None


def is_fixture_tab(rows: list[list[str]]) -> bool:
    """True when a tab carries a group stage's ``Jornada | Grupo`` header."""
    return _fixture_header_at(rows) is not None


def parse_fixture_rounds(rows: list[list[str]]) -> list[FixtureRound]:
    """A fixture list's matches, grouped by jornada in the sheet's order.

    Only the first six columns are read: whatever the sheet keeps to the
    right — the per-team sums the standings tab reads — is working space.
    Played rounds and the next one to play are `open`; later ones fold.
    """
    at = _fixture_header_at(rows)
    if at is None:
        return []
    rounds: dict[str, FixtureRound] = {}
    for row in rows[at + 1 :]:
        jornada, grupo, home, home_points, away_points, away = (
            _cell(row, i) for i in range(6)
        )
        if not (jornada and home and away):
            continue
        rounds.setdefault(jornada, FixtureRound(jornada)).matches.append(
            Match(grupo, home, home_points, away_points, away)
        )
    ordered = list(rounds.values())
    for r in ordered:
        r.open = r.started
    upcoming = next((r for r in ordered if not r.played), None)
    if upcoming is not None:
        upcoming.open = True
    return ordered


def parse_fixture_tab(title: str, rows: list[list[str]]) -> Competition | None:
    """A fixture list standing alone as a `Competition`, or None with no
    matches. The label is the title above the header."""
    rounds = parse_fixture_rounds(rows)
    if not rounds:
        return None
    at = _fixture_header_at(rows) or 0
    above = [_cell(r, 0) for r in rows[:at] if _cell(r, 0)]
    nombre = above[0] if above else title
    return Competition(
        key=_slug(title),
        label=nombre,
        nombre=nombre,
        descripcion="",
        premio="",
        rounds=rounds,
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
    table competitions in the order the owner arranged them — each with the
    fixture tab that follows it, if any — and the tabs that were skipped with
    the reason. Nothing disappears without being named — the
    old reader dropped any tab under six rows in silence, so a half-written
    competition looked identical to one that did not exist.
    """
    h2h_rows: list[list[str]] = []
    competitions: list[Competition] = []
    skipped: list[str] = []

    for workbook in workbooks:
        last_table: Competition | None = None
        for title, rows in workbook:
            previous, last_table = last_table, None
            if is_h2h_tab(rows):
                if h2h_rows:
                    skipped.append(f"«{title}»: ya hay otra pestaña de H2H, se ignora")
                else:
                    h2h_rows = rows
                continue
            if is_fixture_tab(rows):
                if previous is not None:
                    previous.rounds = parse_fixture_rounds(rows)
                    if not previous.rounds:
                        skipped.append(f"«{title}»: sin partidos todavía")
                    continue
                fixtures = parse_fixture_tab(title, rows)
                if fixtures is None:
                    skipped.append(f"«{title}»: sin partidos todavía")
                else:
                    competitions.append(fixtures)
                continue
            if not is_table_tab(rows):
                skipped.append(
                    f"«{title}»: no empieza por «Nombre de la liga» ni es un "
                    "calendario, se ignora"
                )
                continue
            competition = parse_table_tab(title, rows)
            if competition is None:
                skipped.append(f"«{title}»: sin filas de datos todavía")
                continue
            competitions.append(competition)
            last_table = competition

    return h2h_rows, competitions, skipped
