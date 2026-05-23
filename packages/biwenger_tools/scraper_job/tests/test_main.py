"""Tests for the scraper job.

The scraper is Firestore-only now: every board message is hashed into
`comunicados/{season}/messages`, and `participacion`, `clausulazos` and
`tabla_justicia` are rewritten via wipe + bulk-write on each run. These
tests stub out Firestore and the Biwenger client so the behaviour is
exercised without touching the network or a real database.
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from packages.biwenger_tools.scraper_job.main import main


@pytest.fixture(autouse=True)
def mock_external_deps():
    """Stub `config`, the Biwenger client, and the Firestore SDK helpers."""
    with patch(
        "packages.biwenger_tools.scraper_job.main.config",
        **{
            "BIWENGER_EMAIL": "test@example.com",
            "BIWENGER_PASSWORD": "test_password",
            "TEMPORADA_ACTUAL": "25-26",
            "LOGIN_URL": "https://fake-login",
            "ACCOUNT_URL": "https://fake-account",
            "ALL_PLAYERS_DATA_URL": "https://fake-players",
            "LEAGUE_USERS_URL": "https://fake-users",
            "CLAUSULAZOS_URL": "https://fake-clausulazos",
            "BOARD_MESSAGES_URL": "https://fake-board",
            "LEAGUE_ID": "340703",
            # Empty by default → _notify becomes a no-op in tests that
            # don't explicitly enable it. Avoids accidental real HTTP calls.
            "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_ID": "",
        },
    ), patch(
        "packages.biwenger_tools.scraper_job.main.BiwengerClient"
    ) as mock_biwenger_client, patch(
        "packages.biwenger_tools.scraper_job.main.firestore"
    ) as mock_firestore, patch(
        "packages.biwenger_tools.scraper_job.main._existing_message_ids",
        return_value=set(),
    ) as mock_existing_ids, patch(
        "packages.biwenger_tools.scraper_job.main._existing_messages",
        return_value=[],
    ) as mock_existing_msgs:

        mock_biwenger_instance = MagicMock()
        mock_biwenger_client.return_value = mock_biwenger_instance
        mock_biwenger_instance.get_all_players_data_map.return_value = {}
        mock_biwenger_instance.get_all_clausulazos.return_value = {"data": []}

        # Firestore helpers return integers; tests inspect call sites, not
        # values. Side effect on batch_write echoes the input size.
        mock_firestore.delete_collection.return_value = 0
        mock_firestore.batch_write.side_effect = lambda _coll, pairs: len(pairs)

        yield {
            "biwenger": mock_biwenger_instance,
            "firestore": mock_firestore,
            "existing_ids": mock_existing_ids,
            "existing_msgs": mock_existing_msgs,
        }


def _firestore_collections_written(mock_firestore) -> list[str]:
    return [c.args[0] for c in mock_firestore.batch_write.call_args_list]


def test_main_with_new_messages(mock_external_deps):
    """A fresh board message lands in all 4 derived collections."""
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

    main()

    # The 4 collections rewritten in the new-messages path
    assert _firestore_collections_written(mock_external_deps["firestore"]) == [
        "comunicados/25-26/messages",
        "participacion/25-26/authors",
        "clausulazos/25-26/transfers",
        "tabla_justicia/25-26/teams",
    ]
    # Every wipe paired with a write, in the same order
    deleted = [
        c.args[0]
        for c in mock_external_deps["firestore"].delete_collection.call_args_list
    ]
    assert deleted == _firestore_collections_written(mock_external_deps["firestore"])

    # The new comunicado is in the messages payload (first batch_write call)
    messages_pairs = (
        mock_external_deps["firestore"].batch_write.call_args_list[0].args[1]
    )
    assert any("Un nuevo comunicado" in p[1].get("titulo", "") for p in messages_pairs)


def test_main_no_new_messages(mock_external_deps):
    """When every board message already lives in Firestore, only the
    always-rewritten collections (clausulazos + tabla_justicia) get
    touched. Comunicados / participacion stay as-is."""
    content = "Contenido del comunicado."
    existing_hash = hashlib.sha256(f"1672531200{content}".encode("utf-8")).hexdigest()
    mock_external_deps["existing_ids"].return_value = {existing_hash}
    mock_external_deps["biwenger"].get_all_board_messages.return_value = [
        {
            "id": 1,
            "date": 1672531200,
            "author": {"id": 123},
            "title": "Un nuevo comunicado",
            "content": content,
        }
    ]

    main()

    assert _firestore_collections_written(mock_external_deps["firestore"]) == [
        "clausulazos/25-26/transfers",
        "tabla_justicia/25-26/teams",
    ]


# --- Telegram notify on completion ---


def _enable_notify() -> None:
    """Flip the config mock so _notify actually sends."""
    from packages.biwenger_tools.scraper_job import main as scraper_main

    scraper_main.config.TELEGRAM_BOT_TOKEN = "test-token"
    scraper_main.config.TELEGRAM_CHAT_ID = "test-chat"


def test_main_sends_telegram_on_success(mock_external_deps):
    """On success, the scraper notifies the configured chat with both
    counts (messages + clausulazos)."""
    _enable_notify()
    mock_external_deps["biwenger"].get_league_users.return_value = {}
    mock_external_deps["biwenger"].get_all_board_messages.return_value = []
    # parse_clausulazos returns nothing by default in the fixture, so the
    # count will be 0 — assert the wording reflects that.

    with patch(
        "packages.biwenger_tools.scraper_job.main.send_telegram_message"
    ) as mock_send:
        main()

    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs.get("text", "")
    assert "Scraper OK" in text
    assert "sin mensajes nuevos" in text
    # Clausulazos count is always reported, even when 0.
    assert "0 clausulazos" in text


def test_main_sends_telegram_and_reraises_on_error(mock_external_deps):
    """On error, the scraper notifies AND re-raises so Cloud Run marks failed."""
    _enable_notify()
    mock_external_deps["biwenger"].get_all_board_messages.side_effect = RuntimeError(
        "biwenger 503"
    )

    with patch(
        "packages.biwenger_tools.scraper_job.main.send_telegram_message"
    ) as mock_send:
        with pytest.raises(RuntimeError, match="biwenger 503"):
            main()

    mock_send.assert_called_once()
    text = mock_send.call_args.kwargs.get("text", "")
    assert "Scraper falló" in text
    assert "biwenger 503" in text
