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


# --- Configuration -------------------------------------------------------


def test_sheet_ids_split_on_semicolons_and_commas(monkeypatch):
    """Several ids per season travel in one env var.

    The separator is `;` because `gcloud run deploy --set-env-vars` splits its
    own argument on commas: a comma inside a value failed the deploy with
    "Bad syntax for dict arg" before the app could start. Commas are still
    read, for a hand-written local `.env` that never goes through gcloud.
    """
    from packages.biwenger_tools.web import config

    monkeypatch.setenv("TEST_IDS", " a ; b ;; c ")
    assert config._sheet_ids("TEST_IDS") == ["a", "b", "c"]

    monkeypatch.setenv("TEST_IDS", "a,b")
    assert config._sheet_ids("TEST_IDS") == ["a", "b"]

    monkeypatch.delenv("TEST_IDS")
    assert config._sheet_ids("TEST_IDS") == []


# --- A group stage's fixture list, with its results --------------------------

_FIXTURES = [
    ["Copa Santa Claus 26-27 — partidos"],
    ["Rellena Puntos 1 y Puntos 2; la clasificación se actualiza sola."],
    [
        "Jornada",
        "Grupo",
        "Equipo 1",
        "Puntos 1",
        "Puntos 2",
        "Equipo 2",
        "",
        "Grupo",
        "Equipo",
        "PF",
        "PC",
        "Diferencia",
        "Orden",
    ],
    [
        "1",
        "A",
        "Cebollitas FC",
        "60",
        "55",
        "El Tercer Reich",
        "",
        "A",
        "Cebollitas FC",
        "60",
        "55",
        "5",
        "5000060",
    ],
    ["1", "B", "Rayo Entrebirras", "", "", "Kairat FC"],
]


_STANDINGS = _table(
    "Copa Santa Claus 26-27",
    ["Grupo", "Posición", "Equipo", "PF", "PC", "Diferencia"],
    ["A", "1", "Cebollitas FC", "60", "55", "5"],
)


def test_a_fixture_list_joins_the_standings_it_feeds():
    """The matches show inside the cup's own tab, under its table — a second
    tab for the same competition splits what the owner reads as one page."""
    workbook = [("Copa Santa Claus", _STANDINGS), ("Partidos Santa Claus", _FIXTURES)]

    _h2h, comps, skipped = C.read_workbooks([workbook])

    assert skipped == []
    assert [c.label for c in comps] == ["Copa Santa Claus 26-27"]
    assert [r.jornada for r in comps[0].rounds] == ["1"]


def test_a_fixture_list_with_no_table_before_it_is_its_own_competition():
    _h2h, comps, skipped = C.read_workbooks([[("Partidos Santa Claus", _FIXTURES)]])

    assert skipped == []
    assert [c.label for c in comps] == ["Copa Santa Claus 26-27 — partidos"]
    assert comps[0].sections == []


def test_a_fixture_list_never_joins_another_workbooks_table():
    first = [("Copa Castolo", _table("Copa Castolo", ["Equipo", "J1"], ["Rayo", "1"]))]
    second = [("Partidos Santa Claus", _FIXTURES)]

    comps = C.read_workbooks([first, second])[1]

    assert [c.label for c in comps] == [
        "Copa Castolo",
        "Copa Santa Claus 26-27 — partidos",
    ]
    assert comps[0].rounds == []


def test_a_fixture_list_only_joins_the_tab_right_before_it():
    castolo = ("Copa Castolo", _table("Copa Castolo", ["Equipo", "J1"], ["Rayo", "1"]))
    notes = ("Notas", [["apuntes sueltos"]])

    comps = C.read_workbooks([[castolo, notes, ("Partidos", _FIXTURES)]])[1]

    assert [c.label for c in comps] == [
        "Copa Castolo",
        "Copa Santa Claus 26-27 — partidos",
    ]


def test_fixtures_read_as_matches_and_ignore_the_working_columns():
    """The sums to the right feed the standings; they are not the fixtures."""
    comp = C.read_workbooks([[("Partidos Santa Claus", _FIXTURES)]])[1][0]
    (round_one,) = comp.rounds

    played, pending = round_one.matches
    assert (played.grupo, played.home, played.away) == (
        "A",
        "Cebollitas FC",
        "El Tercer Reich",
    )
    assert (played.home_points, played.away_points) == ("60", "55")
    assert played.played and played.outcome == "home"
    assert (pending.home, pending.away) == ("Rayo Entrebirras", "Kairat FC")
    assert not pending.played and pending.outcome == ""
    assert round_one.started and not round_one.played


def test_rounds_follow_the_sheet_and_only_the_next_one_opens():
    """Played rounds and the next to play open; later ones stay folded."""
    rows = _FIXTURES[:3] + [
        ["1", "A", "Cebollitas FC", "60", "60", "El Tercer Reich"],
        ["2", "A", "El Tercer Reich", "", "", "Farolillo AI United"],
        ["3", "A", "Farolillo AI United", "", "", "Cebollitas FC"],
    ]
    comp = C.read_workbooks([[("Partidos", rows)]])[1][0]

    assert [(r.jornada, r.played, r.open) for r in comp.rounds] == [
        ("1", True, True),
        ("2", False, True),
        ("3", False, False),
    ]
    assert comp.rounds[0].matches[0].outcome == "draw"


def test_a_fixture_list_is_not_mistaken_for_the_h2h():
    assert not C.is_h2h_tab(_FIXTURES)
