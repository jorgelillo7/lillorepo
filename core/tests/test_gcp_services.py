from unittest.mock import MagicMock

from core.sdk import gcp

# --- Google Sheets ---


def _service_with(tabs):
    """A Sheets client whose workbook has `tabs` = {title: rows}."""
    service = MagicMock()
    spreadsheets = service.spreadsheets.return_value
    spreadsheets.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": t}} for t in tabs]
    }
    spreadsheets.values.return_value.batchGet.return_value.execute.return_value = {
        "valueRanges": [{"values": rows} for rows in tabs.values()]
    }
    return service, spreadsheets


def test_get_workbook_reads_every_tab_in_two_calls():
    """One metadata call plus one batchGet, whatever the tab count. The loop
    it replaced was one call per tab, which does not scale to a workbook the
    league keeps adding competitions to."""
    service, spreadsheets = _service_with(
        {"Hoja3": [["Jornada", "Partido"]], "Copa Castolo": [["Equipo", "J1"]]}
    )

    result = gcp.get_workbook(service, "spreadsheet_id")

    assert result == [
        ("Hoja3", [["Jornada", "Partido"]]),
        ("Copa Castolo", [["Equipo", "J1"]]),
    ]
    assert spreadsheets.values.return_value.batchGet.call_count == 1
    # Tab titles are quoted, or "Copa Castolo" parses as two ranges.
    ranges = spreadsheets.values.return_value.batchGet.call_args.kwargs["ranges"]
    assert ranges == ["'Hoja3'", "'Copa Castolo'"]


def test_get_workbook_returns_empty_tabs_as_empty():
    """A tab created and not filled in comes back with no values, and must
    not shift the tabs after it."""
    service, spreadsheets = _service_with({"Vacia": [], "Llena": [["a"]]})
    spreadsheets.values.return_value.batchGet.return_value.execute.return_value = {
        "valueRanges": [{}, {"values": [["a"]]}]
    }

    assert gcp.get_workbook(service, "x") == [("Vacia", []), ("Llena", [["a"]])]


def test_get_workbook_with_no_tabs_makes_no_values_call():
    """No tabs means no ranges to ask for — an empty batchGet is an error."""
    service, spreadsheets = _service_with({})

    assert gcp.get_workbook(service, "x") == []
    spreadsheets.values.return_value.batchGet.assert_not_called()
