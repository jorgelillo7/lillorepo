from unittest.mock import MagicMock, patch

import pytest

from packages.biwenger_tools.teams_analyzer.teams_analyzer import main


@pytest.fixture(autouse=True)
def mock_config_module():
    with (
        patch(
            "packages.biwenger_tools.teams_analyzer.config.TELEGRAM_BOT_TOKEN",
            "mock_token",
        ),
        patch(
            "packages.biwenger_tools.teams_analyzer.config.TELEGRAM_CHAT_ID",
            "mock_chat_id",
        ),
    ):
        yield


@pytest.fixture
def mock_all_dependencies():
    with (
        patch(
            "packages.biwenger_tools.teams_analyzer.teams_analyzer.BiwengerClient"
        ) as mock_biwenger_client,
        patch(
            "packages.biwenger_tools.teams_analyzer.teams_analyzer.fetch_all_players"
        ) as mock_fetch_jp,
        patch(
            "packages.biwenger_tools.teams_analyzer.teams_analyzer.check_api_health"
        ) as mock_health,
        patch(
            "packages.biwenger_tools.teams_analyzer.teams_analyzer."
            "send_telegram_message"
        ) as mock_send,
        patch("packages.biwenger_tools.teams_analyzer.teams_analyzer.time.sleep"),
    ):
        mock_biwenger = MagicMock()
        mock_biwenger.user_id = 123  # mánager actual = manager A
        mock_biwenger_client.return_value = mock_biwenger

        biwenger_players = {
            1: {"id": 1, "name": "Player A", "position": 2, "price": 1_000_000},
            2: {"id": 2, "name": "Player B", "position": 4, "price": 1_200_000},
        }
        mock_biwenger.get_all_players_data_map.return_value = biwenger_players
        mock_biwenger.get_league_users.return_value = {
            123: "Manager A",
            456: "Manager B",
        }
        mock_biwenger.get_manager_squad.side_effect = [
            [{"id": 1}],
            [{"id": 2}],
        ]
        mock_biwenger.get_market_players.return_value = [
            {"player": {"id": 1}, "user": None, "price": 0},
        ]

        mock_fetch_jp.return_value = [
            {
                "name": "Player A",
                "slug": "player-a",
                "status": "ok",
                "priceIncrement": 100_000,
                "streak": 3,
                "predict": [{"type": 2, "rate": 350}, {"type": 1, "rate": 200}],
                "nextMatch": {
                    "status": "pending",
                    "playerInLineup": True,
                    "isLocal": True,
                },
            },
            {
                "name": "Player B",
                "slug": "player-b",
                "status": "injured",
                "statusInfo": "Rotura",
                "priceIncrement": -50_000,
                "streak": 0,
                "predict": [],
                "nextMatch": {
                    "status": "pending",
                    "playerInLineup": False,
                    "isLocal": False,
                },
            },
        ]

        yield {
            "biwenger": mock_biwenger,
            "fetch_jp": mock_fetch_jp,
            "health": mock_health,
            "send": mock_send,
        }


def test_main_success(mock_all_dependencies):
    main()

    mock_all_dependencies["health"].assert_called_once()
    mock_all_dependencies["fetch_jp"].assert_called_once()
    mock_all_dependencies["biwenger"].get_all_players_data_map.assert_called_once()
    mock_all_dependencies["biwenger"].get_league_users.assert_called_once()
    mock_all_dependencies["biwenger"].get_market_players.assert_called_once()

    # Manager A es el usuario actual -> "MI EQUIPO"; Manager B -> rival.
    # Mensajes esperados: mi equipo, mercado, manager B
    assert mock_all_dependencies["send"].call_count == 3

    sent_texts = [call.args[2] for call in mock_all_dependencies["send"].call_args_list]
    assert any("MI EQUIPO" in t for t in sent_texts)
    assert any("MERCADO" in t for t in sent_texts)
    assert any("Manager B" in t for t in sent_texts)


def test_main_skips_send_when_no_telegram_creds(mock_all_dependencies):
    with patch(
        "packages.biwenger_tools.teams_analyzer.config.TELEGRAM_BOT_TOKEN", None
    ):
        main()
    mock_all_dependencies["send"].assert_not_called()
