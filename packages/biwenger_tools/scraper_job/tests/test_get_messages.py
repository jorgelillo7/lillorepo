import pytest
import os
import io
import hashlib
from unittest.mock import patch, MagicMock

# Se actualizan las importaciones para que apunten al nuevo nombre de la carpeta
from packages.biwenger_tools.scraper_job.get_messages import main
from packages.biwenger_tools.scraper_job.logic.processing import get_all_board_messages
from core.sdk.biwenger import BiwengerClient

# --- Fixture para mockear servicios externos en todos los tests del archivo ---


@pytest.fixture(autouse=True)
def mock_external_deps():
    """Fixture para mockear servicios externos como Drive y Biwenger."""
    # Las rutas de los patches se actualizan
    with patch(
        "packages.biwenger_tools.scraper_job.get_messages.read_secret_from_file",
        return_value="mock_secret",
    ), patch(
        "packages.biwenger_tools.scraper_job.get_messages.get_google_service"
    ) as mock_gservice, patch(
        "packages.biwenger_tools.scraper_job.get_messages.BiwengerClient"
    ) as mock_biwenger_client, patch(
        "packages.biwenger_tools.scraper_job.get_messages.find_file_on_drive"
    ) as mock_find_file, patch(
        "packages.biwenger_tools.scraper_job.get_messages.download_csv_as_dict"
    ) as mock_download_csv, patch(
        "packages.biwenger_tools.scraper_job.get_messages.upload_csv_to_drive"
    ) as mock_upload_csv, patch(
        "packages.biwenger_tools.scraper_job.get_messages.os.path.exists",
        return_value=True,
    ):

        mock_biwenger_instance = MagicMock()
        mock_biwenger_client.return_value = mock_biwenger_instance
        mock_biwenger_instance.get_all_players_data_map.return_value = {}
        mock_biwenger_instance.get_clausulazos.return_value = {"data": []}

        yield {
            "gservice": mock_gservice,
            "biwenger": mock_biwenger_instance,
            "find_file": mock_find_file,
            "download_csv": mock_download_csv,
            "upload_csv": mock_upload_csv,
        }


# --- Tests para get_all_board_messages (función con paginación) ---


def test_get_all_board_messages_single_page(mock_external_deps):
    """Prueba la descarga de mensajes en una sola página."""
    mock_biwenger = mock_external_deps["biwenger"]
    mock_biwenger.get_board_messages.return_value = {
        "data": [{"id": 1}, {"id": 2}, {"id": 3}]
    }

    messages = get_all_board_messages(mock_biwenger, "http://test.com")

    assert len(messages) == 3
    mock_biwenger.get_board_messages.assert_called_once_with(
        "http://test.com&limit=200&offset=0"
    )


def test_get_all_board_messages_multiple_pages(mock_external_deps):
    """Prueba la descarga con paginación."""
    mock_biwenger = mock_external_deps["biwenger"]
    mock_biwenger.get_board_messages.side_effect = [
        {"data": [{"id": i} for i in range(200)]},
        {"data": [{"id": i} for i in range(200, 250)]},
        {"data": []},
    ]

    messages = get_all_board_messages(mock_biwenger, "http://test.com")

    assert len(messages) == 250
    # Se corrige la aserción: la lógica del scraper solo hace 2 llamadas
    assert mock_biwenger.get_board_messages.call_count == 2
    mock_biwenger.get_board_messages.assert_any_call(
        "http://test.com&limit=200&offset=0"
    )
    mock_biwenger.get_board_messages.assert_any_call(
        "http://test.com&limit=200&offset=200"
    )


# --- Tests para la función principal (main) ---


@patch(
    "packages.biwenger_tools.scraper_job.get_messages.os.path.exists",
    MagicMock(return_value=False),
)
def test_main_with_new_messages(mock_external_deps):
    """Prueba el flujo principal cuando se encuentran nuevos mensajes."""
    mock_external_deps["biwenger"].get_league_users.return_value = {123: "Jorge"}
    mock_external_deps["biwenger"].get_board_messages.return_value = {
        "data": [
            {
                "id": 1,
                "date": 1672531200,
                "author": {"id": 123},
                "title": "Un nuevo comunicado",
                "content": "Contenido del comunicado.",
            }
        ]
    }

    mock_external_deps["find_file"].return_value = None

    # Se llama a la función main() directamente
    main()

    # comunicados + participacion + clausulazos + tabla_justicia
    assert mock_external_deps["upload_csv"].call_count == 4

    call_args = mock_external_deps["upload_csv"].call_args_list[0]
    uploaded_content = call_args[0][3]
    assert "Un nuevo comunicado" in uploaded_content


def test_main_no_new_messages(mock_external_deps):
    """Prueba el flujo principal cuando no hay nuevos mensajes."""
    existing_message = {
        "id_hash": hashlib.sha256(
            "1672531200Contenido del comunicado.".encode("utf-8")
        ).hexdigest(),
        "fecha": "01-01-2023 00:00:00",
        "autor": "Jorge",
        "titulo": "Un nuevo comunicado",
        "contenido": "Contenido del comunicado.",
        "categoria": "comunicado",
    }

    mock_external_deps["biwenger"].get_board_messages.return_value = {
        "data": [
            {
                "id": 1,
                "date": 1672531200,
                "author": {"id": 123},
                "title": "Un nuevo comunicado",
                "content": "Contenido del comunicado.",
            }
        ]
    }

    mock_external_deps["find_file"].return_value = {"id": "fake_id"}
    mock_external_deps["download_csv"].return_value = [existing_message]

    # Se llama a la función main() directamente
    main()

    # Clausulazos siempre se suben (independiente de si hay mensajes nuevos)
    assert mock_external_deps["upload_csv"].call_count == 2
    uploaded_names = [
        call[0][2] for call in mock_external_deps["upload_csv"].call_args_list
    ]
    assert any("clausulazos" in name for name in uploaded_names)
    assert any("tabla_justicia" in name for name in uploaded_names)
