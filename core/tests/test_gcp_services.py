import io
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytz
import pytest
from dateutil import parser

from core.sdk import gcp


# --- Authentication ---


@patch("core.sdk.gcp.service_account")
@patch("core.sdk.gcp.build")
def test_get_google_service(mock_build, mock_service_account):
    """Service is built with the correct credentials."""
    mock_credentials = MagicMock()
    mock_service_account.Credentials.from_service_account_file.return_value = (
        mock_credentials
    )
    service = gcp.get_google_service("test_api", "v1", "service_account.json", ["scope1"])
    mock_service_account.Credentials.from_service_account_file.assert_called_once_with(
        "service_account.json", scopes=["scope1"]
    )
    mock_build.assert_called_once_with("test_api", "v1", credentials=mock_credentials)
    assert service == mock_build.return_value


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


@patch("core.sdk.gcp.MediaIoBaseDownload")
@patch("core.sdk.gcp.io.BytesIO")
def test_download_csv_from_drive(mock_bytesio, mock_download, mock_google_service):
    """File is downloaded and decoded correctly."""
    mock_content = b"header1,header2\nvalue1,value2"
    mock_bytesio_instance = MagicMock()
    mock_bytesio_instance.getvalue.return_value = mock_content
    mock_bytesio.return_value = mock_bytesio_instance
    mock_downloader = MagicMock()
    mock_downloader.next_chunk.side_effect = [(None, False), (None, True)]
    mock_download.return_value = mock_downloader
    result = gcp.download_csv_from_drive(mock_google_service, "test_file_id")
    assert result == mock_content.decode("utf-8")


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


@patch("core.sdk.gcp.MediaIoBaseUpload")
def test_upload_csv_to_drive_update(mock_upload, mock_google_service):
    """Calls update (not create) when the file already exists."""
    mock_google_service.files.return_value.update.return_value.execute.return_value = {}
    gcp.upload_csv_to_drive(
        mock_google_service, "folder_id", "test.csv", "a,b\n1,2", "existing_id"
    )
    mock_google_service.files.return_value.update.assert_called_once()
    mock_google_service.files.return_value.create.assert_not_called()


@patch("core.sdk.gcp.MediaIoBaseUpload")
def test_upload_csv_to_drive_create_new(mock_upload, mock_google_service):
    """Calls create and sets public permissions for a new file."""
    mock_google_service.files.return_value.create.return_value.execute.return_value = {
        "id": "new_id"
    }
    mock_google_service.permissions.return_value.create.return_value.execute.return_value = {}
    gcp.upload_csv_to_drive(
        mock_google_service, "folder_id", "new.csv", "a,b\n1,2", None
    )
    mock_google_service.files.return_value.create.assert_called_once()
    mock_google_service.files.return_value.update.assert_not_called()
    mock_google_service.permissions.return_value.create.assert_called_once()


# --- Google Sheets ---


def test_get_sheets_data_success(mock_sheets_service):
    """Reads data from multiple sheets correctly."""
    mock_sheets_service.spreadsheets.return_value.get.return_value.execute.return_value = {
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
    mock_sheets_service.spreadsheets.return_value.values.return_value.get.return_value.execute = (
        mock_get_values_execute
    )
    result = gcp.get_sheets_data(mock_sheets_service, "spreadsheet_id")
    assert len(result) == 2
    assert result[0]["nombre"] == "Liga Test 1"
    assert result[1]["headers"] == ["ColA", "ColB"]


def test_get_sheets_data_no_data(mock_sheets_service):
    """Handles sheets with no data gracefully."""
    mock_sheets_service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": "HojaVacia"}}]
    }
    mock_get_values_execute = MagicMock()
    mock_get_values_execute.return_value = {"values": []}
    mock_sheets_service.spreadsheets.return_value.values.return_value.get.return_value.execute = (
        mock_get_values_execute
    )
    result = gcp.get_sheets_data(mock_sheets_service, "spreadsheet_id")
    assert result == []


# --- File status helpers ---


def test_get_file_metadata_found(mock_google_drive_service):
    """Found file is processed with correct status and staleness=False."""
    with patch("core.sdk.gcp.datetime") as mock_dt:
        now_madrid = parser.parse("2025-09-04T12:00:00Z").astimezone(
            pytz.timezone("Europe/Madrid")
        )
        mock_dt.now.return_value = now_madrid

        mock_google_drive_service.files().list().execute.return_value = {
            "files": [{"id": "file1", "name": "file1.txt", "modifiedTime": "2025-09-04T10:00:00Z"}]
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
        now_madrid = parser.parse("2025-09-04T12:00:00Z").astimezone(
            pytz.timezone("Europe/Madrid")
        )
        mock_dt.now.return_value = now_madrid

        mock_google_drive_service.files().list().execute.return_value = {
            "files": [{"id": "file1", "name": "file1.txt", "modifiedTime": "2025-08-27T10:00:00Z"}]
        }
        result = gcp.get_file_metadata(
            mock_google_drive_service, "folder_id", ["file1.txt"], ["file1.txt"]
        )
        assert result[0]["is_stale"] is True


def test_get_file_metadata_not_found(mock_google_drive_service):
    """Missing file returns status 'No Encontrado' and staleness=False."""
    with patch("core.sdk.gcp.datetime") as mock_dt:
        now_madrid = parser.parse("2025-09-04T12:00:00Z").astimezone(
            pytz.timezone("Europe/Madrid")
        )
        mock_dt.now.return_value = now_madrid

        mock_google_drive_service.files().list().execute.return_value = {"files": []}
        result = gcp.get_file_metadata(
            mock_google_drive_service, "folder_id", ["missing.txt"], []
        )
        assert result[0]["status"] == "No Encontrado"
        assert result[0]["is_stale"] is False
