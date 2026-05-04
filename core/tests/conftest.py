import json
import os
from unittest.mock import MagicMock

import pytest
import requests_mock

# Importaciones de tu código
from core.sdk.biwenger import BiwengerClient
from .constants import (
    TEST_LOGIN_URL,
    TEST_ACCOUNT_URL,
    TEST_EMAIL,
    TEST_PASSWORD,
    TEST_LEAGUE_ID,
)


# --- Fixtures compartidos y de utilidad ---
@pytest.fixture
def load_json_fixture():
    def _loader(filename):
        file_path = os.path.join(os.path.dirname(__file__), "data", filename)
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    return _loader


# --- Fixtures para biwenger_client.py ---


@pytest.fixture
def biwenger_client_authenticated(load_json_fixture):
    """Fixture que devuelve un cliente de Biwenger autenticado."""
    with requests_mock.Mocker() as m:
        login_data = load_json_fixture("login_response.json")
        account_data = load_json_fixture("account_response.json")
        m.post(TEST_LOGIN_URL, json=login_data, status_code=200)
        m.get(TEST_ACCOUNT_URL, json=account_data, status_code=200)
        return BiwengerClient(
            TEST_EMAIL, TEST_PASSWORD, TEST_LOGIN_URL, TEST_ACCOUNT_URL, TEST_LEAGUE_ID
        )


# --- Fixtures para utils.py ---


@pytest.fixture
def mock_filesystem(tmp_path):
    """
    Fixture que simula un sistema de archivos en un directorio temporal.
    'tmp_path' es una fixture de pytest que crea un directorio temporal seguro.
    """

    def _create_mock_file(filename, content):
        file_path = tmp_path / filename
        file_path.write_text(content)
        return str(file_path)

    return _create_mock_file


@pytest.fixture
def mock_google_drive_service():
    """
    Fixture que simula el servicio de Google Drive.
    """
    service = MagicMock()
    files_mock = MagicMock()
    service.files.return_value = files_mock
    list_mock = files_mock.list
    execute_mock = list_mock.return_value
    execute_mock.execute.return_value = {}
    return service


# --- Fixtures para google_services.py ---


@pytest.fixture
def mock_google_service():
    """Fixture que devuelve un mock de un servicio de la API de Google."""
    return MagicMock()


@pytest.fixture
def mock_sheets_service():
    """Fixture que devuelve un mock de un servicio de la API de Google Sheets."""
    service = MagicMock()
    return service
