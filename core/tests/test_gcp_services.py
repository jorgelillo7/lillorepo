from unittest.mock import MagicMock

from core.sdk import gcp

# --- Google Sheets ---


def test_get_sheets_data_success(mock_sheets_service):
    """Reads data from multiple sheets correctly."""
    spreadsheets = mock_sheets_service.spreadsheets.return_value
    spreadsheets.get.return_value.execute.return_value = {
        "sheets": [
            {"properties": {"title": "Hoja1"}},
            {"properties": {"title": "Hoja2"}},
        ]
    }
    mock_get_values_execute = MagicMock()
    mock_get_values_execute.side_effect = [
        {
            "values": [
                ["Nombre de la Liga:", "Liga Test 1"],
                ["Descripción:", "Desc. 1"],
                ["Premio:", "100€"],
                ["", ""],
                ["Col1", "Col2"],
                ["val1", "val2"],
            ]
        },
        {
            "values": [
                ["Nombre de la Liga:", "Liga Test 2"],
                ["Descripción:", "Desc. 2"],
                ["Premio:", "200€"],
                ["", ""],
                ["ColA", "ColB"],
                ["valA", "valB"],
            ]
        },
    ]
    spreadsheets.values.return_value.get.return_value.execute = mock_get_values_execute
    result = gcp.get_sheets_data(mock_sheets_service, "spreadsheet_id")
    assert len(result) == 2
    assert result[0]["nombre"] == "Liga Test 1"
    assert result[1]["headers"] == ["ColA", "ColB"]


def test_get_sheets_data_no_data(mock_sheets_service):
    """Handles sheets with no data gracefully."""
    spreadsheets = mock_sheets_service.spreadsheets.return_value
    spreadsheets.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": "HojaVacia"}}]
    }
    mock_get_values_execute = MagicMock()
    mock_get_values_execute.return_value = {"values": []}
    spreadsheets.values.return_value.get.return_value.execute = mock_get_values_execute
    result = gcp.get_sheets_data(mock_sheets_service, "spreadsheet_id")
    assert result == []
