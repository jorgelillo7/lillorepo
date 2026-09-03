"""Tests for the recognised-waters download and parser.

Every regression this script has had lived in one of three places: page
furniture read as data, table cells that wrap across lines, and a refusal from
the host mistaken for the document moving. All are exercised against synthetic
text and an injected fetch, so neither a PDF nor the network is needed.

Column starts are derived per page from the rows that come out in three
pieces, so the alignment below is the fixture, not decoration — only the
relative positions matter, not the real document's widths.
"""

import pytest

from packages.be_water.scripts.refresh_aesan_snapshot import (
    BACKOFF_CAP_SECONDS,
    _backoff,
    _download,
    parse_pages,
)

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


# The host answers a burst with an HTML "Sorry" page, byte-for-byte as
# unreadable as a dead link's. Telling the two apart is the difference between
# "re-run it" and "the registry is gone".
_THROTTLED = b"<html><head><title>Sorry - 35884773</title></head>429</html>"
_GONE = b"<html><head><title>Page not found</title></head></html>"
_PDF = b"%PDF-1.7\nthe list"


def _fetcher(*responses):
    """A `fetch` stub yielding the given responses, then repeating the last."""
    queue = list(responses)
    calls: list[str] = []

    def fetch(url):
        calls.append(url)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    fetch.calls = calls
    return fetch


def _recorder():
    """A `sleep` stub that waits for nothing and remembers the delays."""
    delays: list[float] = []
    return delays, delays.append


def test_a_throttled_download_is_retried_and_succeeds():
    fetch = _fetcher((429, _THROTTLED, None), (200, _PDF, None))
    delays, sleep = _recorder()

    assert _download(fetch=fetch, sleep=sleep) == _PDF
    assert len(fetch.calls) == 2
    assert len(delays) == 1


def test_a_download_throttled_every_time_gives_up_naming_the_throttle():
    fetch = _fetcher((429, _THROTTLED, None))
    _, sleep = _recorder()

    with pytest.raises(SystemExit) as exit_info:
        _download(fetch=fetch, sleep=sleep, attempts=4)

    message = str(exit_info.value)
    assert len(fetch.calls) == 4
    assert "throttling" in message
    assert "429" in message
    # The wrong diagnosis is the whole point of the fix: it must not say this.
    assert "probably moved" not in message


def test_a_moved_document_fails_immediately_without_retrying():
    fetch = _fetcher((404, _GONE, None))
    delays, sleep = _recorder()

    with pytest.raises(SystemExit) as exit_info:
        _download(fetch=fetch, sleep=sleep)

    assert len(fetch.calls) == 1
    assert delays == []
    assert "probably moved" in str(exit_info.value)


def test_a_200_that_is_not_a_pdf_still_refuses():
    fetch = _fetcher((200, _GONE, None))
    _, sleep = _recorder()

    with pytest.raises(SystemExit) as exit_info:
        _download(fetch=fetch, sleep=sleep, attempts=2)

    assert "not a PDF" in str(exit_info.value)


def test_the_refusal_carries_the_page_that_caused_it():
    fetch = _fetcher((429, _THROTTLED, None))
    _, sleep = _recorder()

    with pytest.raises(SystemExit) as exit_info:
        _download(fetch=fetch, sleep=sleep, attempts=2)

    # Without the evidence, the next failure costs another investigation.
    assert "Sorry - 35884773" in str(exit_info.value)


def test_retry_after_is_honoured_but_capped():
    assert _backoff(1, "30") == 30.0
    assert _backoff(1, "3600") == BACKOFF_CAP_SECONDS
    assert _backoff(1, None) == 2.0
    assert _backoff(1, "not a number") == 2.0
