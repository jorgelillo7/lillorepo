import hashlib
from unittest.mock import patch, MagicMock

import pytest

from packages.biwenger_tools.scraper_job.main import main

# --- Fixture para mockear servicios externos en todos los tests del archivo ---


@pytest.fixture(autouse=True)
def mock_external_deps():
    """Fixture para mockear servicios externos como Drive y Biwenger."""
    # Las rutas de los patches se actualizan
    with patch(
        "packages.biwenger_tools.scraper_job.main.config",
        **{
            "BIWENGER_EMAIL": "test@example.com",
            "BIWENGER_PASSWORD": "test_password",
            "GDRIVE_FOLDER_ID": "mock_folder_id",
            "SERVICE_ACCOUNT_PATH": "/fake/sa.json",
            "SCOPES": [],
            "TEMPORADA_ACTUAL": "25-26",
            "CLAUSULAZOS_FILENAME_BASE": "clausulazos",
            "TABLA_JUSTICIA_FILENAME_BASE": "tabla_justicia",
            "LOGIN_URL": "https://fake-login",
            "ACCOUNT_URL": "https://fake-account",
            "ALL_PLAYERS_DATA_URL": "https://fake-players",
            "LEAGUE_USERS_URL": "https://fake-users",
            "CLAUSULAZOS_URL": "https://fake-clausulazos",
            "BOARD_MESSAGES_URL": "https://fake-board",
            "LEAGUE_ID": "340703",
            # Empty by default → _notify becomes a no-op in tests that don't
            # explicitly enable it. Avoids accidental real HTTP calls.
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_ID": "",
        },
    ), patch(
        "packages.biwenger_tools.scraper_job.main.get_google_service"
    ) as mock_gservice, patch(
        "packages.biwenger_tools.scraper_job.main.BiwengerClient"
    ) as mock_biwenger_client, patch(
        "packages.biwenger_tools.scraper_job.main.find_file_on_drive"
    ) as mock_find_file, patch(
        "packages.biwenger_tools.scraper_job.main.download_csv_as_dict"
    ) as mock_download_csv, patch(
        "packages.biwenger_tools.scraper_job.main.upload_csv_to_drive"
    ) as mock_upload_csv, patch(
        "packages.biwenger_tools.scraper_job.main.firestore"
    ) as mock_firestore, patch(
        "packages.biwenger_tools.scraper_job.main.os.path.exists",
        return_value=True,
    ):

        mock_biwenger_instance = MagicMock()
        mock_biwenger_client.return_value = mock_biwenger_instance
        mock_biwenger_instance.get_all_players_data_map.return_value = {}
        mock_biwenger_instance.get_all_clausulazos.return_value = {"data": []}

        # Firestore helpers return ints; tests inspect the call sites, not values.
        mock_firestore.delete_collection.return_value = 0
        mock_firestore.batch_write.side_effect = lambda _coll, pairs: len(pairs)

        yield {
            "gservice": mock_gservice,
            "biwenger": mock_biwenger_instance,
            "find_file": mock_find_file,
            "download_csv": mock_download_csv,
            "upload_csv": mock_upload_csv,
            "firestore": mock_firestore,
        }


# --- Tests para la función principal (main) ---


@patch(
    "packages.biwenger_tools.scraper_job.main.os.path.exists",
    MagicMock(return_value=False),
)
def test_main_with_new_messages(mock_external_deps):
    """Prueba el flujo principal cuando se encuentran nuevos mensajes."""
    mock_external_deps["biwenger"].get_league_users.return_value = {123: "Jorge"}
    mock_external_deps["biwenger"].get_all_board_messages.return_value = [
        {
            "id": 1,
            "date": 1672531200,
            "author": {"id": 123},
            "title": "Un nuevo comunicado",
            "content": "Contenido del comunicado.",
        }
    ]

    mock_external_deps["find_file"].return_value = None

    # Se llama a la función main() directamente
    main()

    # comunicados + participacion + clausulazos + tabla_justicia
    assert mock_external_deps["upload_csv"].call_count == 4

    call_args = mock_external_deps["upload_csv"].call_args_list[0]
    uploaded_content = call_args[0][3]
    assert "Un nuevo comunicado" in uploaded_content

    # Dual-write: same 4 collections also land in Firestore.
    firestore_collections = [
        call.args[0]
        for call in mock_external_deps["firestore"].batch_write.call_args_list
    ]
    assert firestore_collections == [
        "comunicados/25-26/messages",
        "participacion/25-26/authors",
        "clausulazos/25-26/transfers",
        "tabla_justicia/25-26/teams",
    ]
    # Firestore wipe-then-write contract: every batch_write is paired with
    # a delete_collection on the same collection, in the same order.
    deleted_collections = [
        call.args[0]
        for call in mock_external_deps["firestore"].delete_collection.call_args_list
    ]
    assert deleted_collections == firestore_collections


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

    mock_external_deps["biwenger"].get_all_board_messages.return_value = [
        {
            "id": 1,
            "date": 1672531200,
            "author": {"id": 123},
            "title": "Un nuevo comunicado",
            "content": "Contenido del comunicado.",
        }
    ]

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

    # Same parity in Firestore: only clausulazos + tabla_justicia get
    # rewritten when there are no new messages.
    firestore_collections = [
        call.args[0]
        for call in mock_external_deps["firestore"].batch_write.call_args_list
    ]
    assert firestore_collections == [
        "clausulazos/25-26/transfers",
        "tabla_justicia/25-26/teams",
    ]


# --- Telegram notify on completion ---


def _enable_notify(monkeypatch_config) -> None:
    """Flip the config mock so _notify actually sends."""
    cfg = monkeypatch_config["config"] if "config" in monkeypatch_config else None
    if cfg is None:
        # The fixture patches the `config` symbol module-wide; we set the
        # values via module attribute access.
        from packages.biwenger_tools.scraper_job import main as scraper_main

        scraper_main.config.TELEGRAM_BOT_TOKEN = "test-token"
        scraper_main.config.TELEGRAM_CHAT_ID = "test-chat"


def test_main_sends_telegram_on_success(mock_external_deps):
    """On success, the scraper notifies the configured chat."""
    _enable_notify(mock_external_deps)
    mock_external_deps["biwenger"].get_league_users.return_value = {}
    mock_external_deps["biwenger"].get_all_board_messages.return_value = []
    mock_external_deps["find_file"].return_value = None

    with patch(
        "packages.biwenger_tools.scraper_job.main.send_telegram_message"
    ) as mock_send:
        main()

    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs.get("text", "")
    assert "Scraper OK" in text
    assert "sin mensajes nuevos" in text


def test_main_sends_telegram_and_reraises_on_error(mock_external_deps):
    """On error, the scraper notifies AND re-raises so Cloud Run marks failed."""
    _enable_notify(mock_external_deps)
    mock_external_deps["biwenger"].get_all_board_messages.side_effect = RuntimeError(
        "biwenger 503"
    )
    mock_external_deps["find_file"].return_value = None

    with patch(
        "packages.biwenger_tools.scraper_job.main.send_telegram_message"
    ) as mock_send:
        with pytest.raises(RuntimeError, match="biwenger 503"):
            main()

    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs.get("text", "")
    assert "Scraper falló" in text
    assert "biwenger 503" in text
