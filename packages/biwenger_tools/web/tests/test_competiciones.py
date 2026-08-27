"""Tests for reading the competitions workbook.

The shapes here are the ones the league's own sheets use, transcribed from
the 25-26 exports rather than invented: `Nombre de la liga` in A1, a blank
row 4, the header on row 5, and — in the Copa Santa Claus — two group tables
stacked in a single tab.
"""

from packages.biwenger_tools.web import competiciones as C


def _table(nombre, header, *rows, descripcion="una descripción", premio="la gloria"):
    """A tab in the awards format. Row 4 is blank, exactly as the API sends
    it: `values.get` keeps interior blank rows as `[]`."""
    return [
        ["Nombre de la liga", nombre],
        ["Descripción", descripcion],
        ["Premio", premio],
        [],
        list(header),
    ] + [list(r) for r in rows]


# --- Classifying a tab ---------------------------------------------------


def test_the_h2h_tab_is_found_by_its_header_not_its_name():
    """The owner renames tabs. `Hoja3` held the fixtures all season."""
    rows = [
        ["Calendario H2H"],
        ["Introduce los puntos"],
        ["Jornada", "Partido", "Equipo 1", "Puntos 1", "Puntos 2", "Equipo 2"],
        ["1", "1", "Fabio", "78", "43", "Rubén"],
    ]
    assert C.is_h2h_tab(rows)
    assert not C.is_table_tab(rows)


def test_a_tab_in_neither_format_is_reported_not_dropped():
    """The old reader skipped any tab under six rows in silence, so a
    half-written competition looked exactly like one that did not exist."""
    workbook = [("Notas sueltas", [["algo"], ["otra cosa"]])]

    h2h, comps, skipped = C.read_workbooks([workbook])

    assert (h2h, comps) == ([], [])
    assert len(skipped) == 1 and "Notas sueltas" in skipped[0]


def test_a_table_tab_with_no_data_rows_yet_is_reported():
    """A competition created but not filled in is a normal state — it just
    has to say so instead of vanishing."""
    workbook = [("Copa Nueva", _table("Copa Nueva", ["Equipo", "Puntos"]))]

    _h2h, comps, skipped = C.read_workbooks([workbook])

    assert comps == []
    assert len(skipped) == 1 and "sin filas de datos" in skipped[0]


# --- Sections ------------------------------------------------------------


def test_a_group_stage_splits_into_one_section_per_group():
    """The 25-26 Copa Santa Claus stacks GRUPO A and GRUPO B in one tab, each
    introduced by its own header row. Reading only the first header rendered
    GRUPO B's header as if it were a team — the defect this pins."""
    tab = _table(
        "Copa Santa Claus",
        ["GRUPO A", "Jugados", "Puntos a favor", "Puntos en contra", "Balance"],
        ["La Luceneta", "0"],
        ["Los caídos de la jornada", "0"],
        ["GRUPO B", "Jugados", "Puntos a favor", "Puntos en contra", "Balance"],
        ["Kairat FC", "0"],
        ["Rayo Entrebirras", "0"],
    )

    competition = C.parse_table_tab("Copa Santa Claus", tab)

    assert [s.titulo for s in competition.sections] == ["GRUPO A", "GRUPO B"]
    assert [len(s.rows) for s in competition.sections] == [2, 2]
    # No group name ever lands in a data row.
    every_first_cell = [r[0] for s in competition.sections for r in s.rows]
    assert "GRUPO B" not in every_first_cell
    # With groups, column A labels the group, so it has no column header.
    assert competition.sections[0].headers[0] == ""


def test_a_single_table_keeps_its_first_column_header():
    """`Equipo | Puntos` is a column header, not a section title — only a
    repeated header row means a section."""
    tab = _table("Pichichi", ["Equipo", "Goles"], ["Rayo", "47"], ["Kairat", "26"])

    competition = C.parse_table_tab("Trofeo D", tab)

    assert len(competition.sections) == 1
    assert competition.sections[0].titulo == ""
    assert competition.sections[0].headers == ["Equipo", "Goles"]
    assert len(competition.sections[0].rows) == 2


def test_the_tab_takes_its_label_from_the_sheet_not_the_tab_name():
    """The trofeos tabs are called `Trofeo A`…`Trofeo D` while A1 carries the
    real name. The nav has to read `Pichichi`, not `Trofeo D`."""
    competition = C.parse_table_tab("Trofeo D", _table("Pichichi", ["Equipo"], ["X"]))

    assert competition.label == "Pichichi"
    assert competition.key == "trofeo-d"


def test_ragged_rows_survive():
    """The API truncates each row at its last non-empty cell, so a row can be
    shorter than the header."""
    tab = _table("Copa", ["Equipo", "Jugados", "Balance"], ["La Luceneta", "0"])

    competition = C.parse_table_tab("Copa", tab)

    assert competition.sections[0].rows == [["La Luceneta", "0"]]


# --- Several workbooks ---------------------------------------------------


def test_workbooks_concatenate_in_order():
    """25-26 lived across two spreadsheets. Listing both ids rescues all of
    it without migrating a single row."""
    ligas = [("Copa Castolo", _table("Copa Castolo", ["Equipo", "J1"], ["A", "60"]))]
    trofeos = [("Trofeo A", _table("Records", ["Record", "Equipo"], ["Máximo", "B"]))]

    _h2h, comps, skipped = C.read_workbooks([ligas, trofeos])

    assert [c.label for c in comps] == ["Copa Castolo", "Records"]
    assert skipped == []


def test_a_second_h2h_tab_is_refused():
    """Two fixture blocks would silently pick one. Say which was ignored."""
    rows = [["Jornada", "Partido", "Equipo 1"], ["1", "1", "Fabio"]]
    workbook = [("H2H", rows), ("H2H copia", rows)]

    h2h, _comps, skipped = C.read_workbooks([workbook])

    assert h2h == rows
    assert len(skipped) == 1 and "ya hay otra pestaña de H2H" in skipped[0]
