from unittest.mock import MagicMock, patch

import pytest

from packages.biwenger_tools.teams_analyzer.main import main

_DUMMY_IMG = b"PNG"


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
        patch(
            "packages.biwenger_tools.teams_analyzer.config.ANALYSIS_MODE",
            "all",
        ),
    ):
        yield


@pytest.fixture
def mock_all_dependencies():
    with (
        patch(
            "packages.biwenger_tools.teams_analyzer.main.BiwengerClient"
        ) as mock_biwenger_client,
        patch(
            "packages.biwenger_tools.teams_analyzer.main.fetch_all_players"
        ) as mock_fetch_jp,
        patch(
            "packages.biwenger_tools.teams_analyzer.main.check_api_health"
        ) as mock_health,
        patch(
            "packages.biwenger_tools.teams_analyzer.main.send_telegram_photo"
        ) as mock_send,
        patch(
            "packages.biwenger_tools.teams_analyzer.main.build_table_image",
            return_value=_DUMMY_IMG,
        ),
        patch("packages.biwenger_tools.teams_analyzer.main.time.sleep"),
        patch(
            "packages.biwenger_tools.teams_analyzer.main.time.time",
            return_value=1_800_000_000,
        ),
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
        # Player A: no clause lock; Player B: locked for 9 more days
        mock_biwenger.get_manager_squad.side_effect = [
            [{"id": 1, "owner": {"clause": 1_530_000}}],
            [
                {
                    "id": 2,
                    "owner": {
                        "clause": 1_836_000,
                        "clauseLockedUntil": 1_800_000_000 + 9 * 86400,
                    },
                }
            ],
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


def _sent_captions(mock_send):
    # send_telegram_photo(token, chat_id, image_bytes, caption)
    return [call.args[3] for call in mock_send.call_args_list]


def test_main_success(mock_all_dependencies):
    main()

    mock_all_dependencies["health"].assert_called_once()
    mock_all_dependencies["fetch_jp"].assert_called_once()
    mock_all_dependencies["biwenger"].get_all_players_data_map.assert_called_once()
    mock_all_dependencies["biwenger"].get_league_users.assert_called_once()
    mock_all_dependencies["biwenger"].get_market_players.assert_called_once()

    # Mode "all": mi equipo image + Manager B image + mercado image = 3 photos
    assert mock_all_dependencies["send"].call_count == 3

    captions = _sent_captions(mock_all_dependencies["send"])
    assert any("Mi equipo" in c for c in captions)
    assert any("Mercado" in c for c in captions)
    assert any("Manager B" in c for c in captions)


def test_main_skips_send_when_no_telegram_creds(mock_all_dependencies):
    with patch(
        "packages.biwenger_tools.teams_analyzer.config.TELEGRAM_BOT_TOKEN", None
    ):
        main()
    mock_all_dependencies["send"].assert_not_called()


def test_main_aborts_silently_when_jp_health_fails(mock_all_dependencies):
    """If the JP token rotated or the API is down, the orchestrator must NOT
    fall through to fetching/sending — it would push a stale or empty digest.
    """
    mock_all_dependencies["health"].side_effect = RuntimeError("token rotated")

    main()

    mock_all_dependencies["fetch_jp"].assert_not_called()
    mock_all_dependencies["biwenger"].get_all_players_data_map.assert_not_called()
    mock_all_dependencies["send"].assert_not_called()


def test_main_aborts_silently_when_jp_fetch_fails(mock_all_dependencies):
    """If JP responds to the health-check but the full fetch fails, we still
    don't want to call Biwenger and ship half-data to Telegram."""
    mock_all_dependencies["fetch_jp"].side_effect = RuntimeError("connection reset")

    main()

    mock_all_dependencies["biwenger"].get_all_players_data_map.assert_not_called()
    mock_all_dependencies["send"].assert_not_called()


def test_main_with_empty_squad_still_sends_market(mock_all_dependencies):
    """An empty squad shouldn't crash — market and rivals digest still go out."""
    mock_all_dependencies["biwenger"].get_manager_squad.side_effect = [[], []]

    main()

    assert mock_all_dependencies["send"].call_count >= 2
    captions = _sent_captions(mock_all_dependencies["send"])
    assert any("Mi equipo" in c for c in captions)
    assert any("Mercado" in c for c in captions)
