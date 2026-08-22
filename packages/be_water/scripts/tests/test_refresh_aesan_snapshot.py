"""Tests for the recognised-waters parser.

Every regression this script has had lived in the same two places: page
furniture read as data, and table cells that wrap across lines. Both are
exercised here against synthetic layout text, so no PDF is needed.

Column starts are derived per page from the rows that come out in three
pieces, so the alignment below is the fixture, not decoration — only the
relative positions matter, not the real document's widths.
"""

from packages.be_water.scripts.refresh_aesan_snapshot import parse_pages

_SPAIN = "  List of natural mineral waters recognised by Spain"
_THIRD = "  List of natural mineral waters from third countries recognised by Spain"
_HEADER = "     Trade description    Name of source     Place of exploitation"


def _page(*lines: str) -> str:
    return "\n".join(("            Last update 16.07.2026", *lines))


def _row(name: str, spring: str, place: str) -> str:
    return f"  {name:<22}{spring:<19}{place}"


def _wrap(place: str) -> str:
    return f"  {'':<22}{'':<19}{place}"


def test_reads_a_plain_row():
    date, entries = parse_pages(
        [
            _page(
                _SPAIN,
                _HEADER,
                _row("Peñaclara", "Peñaclara", "Torrecilla (La Rioja)"),
                _row("Sousas", "Sousas II", "Verín (Ourense)"),
            )
        ]
    )
    assert date == "16/07/2026"
    assert entries == [
        {
            "name": "Peñaclara",
            "spring": "Peñaclara",
            "place": "Torrecilla",
            "province": "La Rioja",
        },
        {
            "name": "Sousas",
            "spring": "Sousas II",
            "place": "Verín",
            "province": "Ourense",
        },
    ]


def test_a_two_line_place_wraps_above_its_row():
    _, entries = parse_pages(
        [
            _page(
                _SPAIN,
                _HEADER,
                _row("Cantalar", "Cantalar", "Moratalla (Murcia)"),
                _wrap("Pedralba de la Pradería"),
                _row("Calabor", "Calabor", "(Zamora)"),
            )
        ]
    )
    assert [e["name"] for e in entries] == ["Cantalar", "Calabor"]
    assert entries[1]["place"] == "Pedralba de la Pradería"
    assert entries[1]["province"] == "Zamora"


def test_a_three_line_place_wraps_below_its_row():
    _, entries = parse_pages(
        [
            _page(
                _SPAIN,
                _HEADER,
                _row("La Serreta", "La Serreta", "PARTIDA JUNCAREJOS."),
                _wrap("LA FONT DE LA"),
                _wrap("FIGUERA (VALENCIA)"),
            )
        ]
    )
    assert entries == [
        {
            "name": "La Serreta",
            "spring": "La Serreta",
            "place": "PARTIDA JUNCAREJOS. LA FONT DE LA FIGUERA",
            "province": "VALENCIA",
        }
    ]


def test_repeated_page_furniture_is_not_read_as_a_water():
    # The bug fixed in d462fbb: headers repeat on every page and once ate four
    # waters. A page break must not cost an entry or invent one.
    _, entries = parse_pages(
        [
            _page(_SPAIN, _HEADER, _row("Bezoya", "Bezoya", "Ortigosa (Segovia)")),
            _page(_HEADER, _row("Solares", "Fuente Solares", "Solares (Cantabria)")),
        ]
    )
    assert [e["name"] for e in entries] == ["Bezoya", "Solares"]


def test_other_countries_and_third_country_tables_are_excluded():
    _, entries = parse_pages(
        [
            _page(
                "  List of natural mineral waters recognised by Greece",
                _HEADER,
                _row("Zagori", "Karakori", "Perivleptou (Ioannina)"),
                _SPAIN,
                _HEADER,
                _row("Veri", "Veri 1", "Bisaurri (Huesca)"),
                _THIRD,
                _HEADER,
                _row("Decantae", "Decantae", "Abergele (Reino Unido)"),
            )
        ]
    )
    assert [e["name"] for e in entries] == ["Veri"]
