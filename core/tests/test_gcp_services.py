from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from dateutil import parser

from core.sdk import gcp

MADRID_TZ = ZoneInfo("Europe/Madrid")


# --- Google Drive ---


def test_find_file_on_drive_found(mock_google_service):
    """Returns the file when found."""
    mock_response = {"files": [{"id": "file1", "name": "file1.txt"}]}
    mock_google_service.files().list().execute.return_value = mock_response
    result = gcp.find_file_on_drive(mock_google_service, "file1.txt", "folder123")
    assert result == mock_response["files"][0]


def test_find_file_on_drive_not_found(mock_google_service):
    """Returns None when the file is not found."""
    mock_google_service.files().list().execute.return_value = {"files": []}
    result = gcp.find_file_on_drive(mock_google_service, "missing.txt", "folder123")
    assert result is None


@patch("core.sdk.gcp.download_csv_from_drive")
def test_download_csv_as_dict_success(mock_download_csv):
    """CSV string is converted to a list of dicts correctly."""
    mock_download_csv.return_value = "col1,col2\nval1,val2\nval3,val4"
    result = gcp.download_csv_as_dict(None, "file_id")
    assert len(result) == 2
    assert result[0] == {"col1": "val1", "col2": "val2"}


def test_download_csv_as_dict_no_file_id():
    """Raises FileNotFoundError when no file ID is provided."""
    with pytest.raises(FileNotFoundError):
        gcp.download_csv_as_dict(None, None)


def test_upload_csv_to_drive_update_sends_actual_content(mock_google_service):
    """The CSV string is uploaded verbatim when updating an existing file."""
    captured = {}

    def fake_media(buffer, mimetype, resumable):
        captured["body"] = buffer.read().decode("utf-8")
        captured["mimetype"] = mimetype
        return MagicMock()

    csv_payload = "a,b\n1,2\n3,4"
    with patch("core.sdk.gcp.MediaIoBaseUpload", side_effect=fake_media):
        gcp.upload_csv_to_drive(
            mock_google_service, "folder_id", "test.csv", csv_payload, "existing_id"
        )

    assert captured["body"] == csv_payload
    assert captured["mimetype"] == "text/csv"
    mock_google_service.files.return_value.update.assert_called_once()
    update_kwargs = mock_google_service.files.return_value.update.call_args.kwargs
    assert update_kwargs["fileId"] == "existing_id"
    mock_google_service.files.return_value.create.assert_not_called()


def test_upload_csv_to_drive_create_new_makes_public(mock_google_service):
    """A brand-new file is created with the right metadata and made public."""
    captured = {}

    def fake_media(buffer, mimetype, resumable):
        captured["body"] = buffer.read().decode("utf-8")
        return MagicMock()

    files = mock_google_service.files.return_value
    permissions = mock_google_service.permissions.return_value
    files.create.return_value.execute.return_value = {"id": "new_id"}

    with patch("core.sdk.gcp.MediaIoBaseUpload", side_effect=fake_media):
        gcp.upload_csv_to_drive(
            mock_google_service, "folder_id", "new.csv", "a,b\n1,2", None
        )

    create_kwargs = files.create.call_args.kwargs
    assert create_kwargs["body"] == {"name": "new.csv", "parents": ["folder_id"]}
    assert captured["body"] == "a,b\n1,2"

    permissions.create.assert_called_once()
    perm_kwargs = permissions.create.call_args.kwargs
    assert perm_kwargs["fileId"] == "new_id"
    assert perm_kwargs["body"] == {"type": "anyone", "role": "reader"}


def test_upload_then_download_roundtrips(mock_google_service):
    """Whatever is uploaded must come back identically via download_csv_as_dict."""
    captured = {}

    def fake_media(buffer, mimetype, resumable):
        captured["body"] = buffer.read()
        return MagicMock()

    payload = "id_hash,fecha,autor\nabc,01-01-2025,Jorge\n"
    with patch("core.sdk.gcp.MediaIoBaseUpload", side_effect=fake_media):
        gcp.upload_csv_to_drive(
            mock_google_service, "folder_id", "x.csv", payload, "existing"
        )

    # Round-trip: parse what we sent
    with patch(
        "core.sdk.gcp.download_csv_from_drive",
        return_value=captured["body"].decode("utf-8"),
    ):
        rows = gcp.download_csv_as_dict(mock_google_service, "existing")

    assert rows == [{"id_hash": "abc", "fecha": "01-01-2025", "autor": "Jorge"}]


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


# --- File status helpers ---


def test_get_file_metadata_found(mock_google_drive_service):
    """Found file is processed with correct status and staleness=False."""
    with patch("core.sdk.gcp.datetime") as mock_dt:
        now_madrid = parser.parse("2025-09-04T12:00:00Z").astimezone(MADRID_TZ)
        mock_dt.now.return_value = now_madrid

        mock_google_drive_service.files().list().execute.return_value = {
            "files": [
                {
                    "id": "file1",
                    "name": "file1.txt",
                    "modifiedTime": "2025-09-04T10:00:00Z",
                }
            ]
        }
        result = gcp.get_file_metadata(
            mock_google_drive_service, "folder_id", ["file1.txt"], []
        )
        assert len(result) == 1
        assert result[0]["status"] == "Encontrado"
        assert result[0]["is_stale"] is False


def test_get_file_metadata_stale(mock_google_drive_service):
    """Dynamic file older than 7 days is marked as stale."""
    with patch("core.sdk.gcp.datetime") as mock_dt:
        now_madrid = parser.parse("2025-09-04T12:00:00Z").astimezone(MADRID_TZ)
        mock_dt.now.return_value = now_madrid

        mock_google_drive_service.files().list().execute.return_value = {
            "files": [
                {
                    "id": "file1",
                    "name": "file1.txt",
                    "modifiedTime": "2025-08-27T10:00:00Z",
                }
            ]
        }
        result = gcp.get_file_metadata(
            mock_google_drive_service, "folder_id", ["file1.txt"], ["file1.txt"]
        )
        assert result[0]["is_stale"] is True


def test_get_file_metadata_not_found(mock_google_drive_service):
    """Missing file returns status 'No Encontrado' and staleness=False."""
    with patch("core.sdk.gcp.datetime") as mock_dt:
        now_madrid = parser.parse("2025-09-04T12:00:00Z").astimezone(MADRID_TZ)
        mock_dt.now.return_value = now_madrid

        mock_google_drive_service.files().list().execute.return_value = {"files": []}
        result = gcp.get_file_metadata(
            mock_google_drive_service, "folder_id", ["missing.txt"], []
        )
        assert result[0]["status"] == "No Encontrado"
        assert result[0]["is_stale"] is False
