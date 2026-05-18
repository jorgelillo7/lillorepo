"""Tests for the Biwenger bot webhook."""

from unittest.mock import patch

import pytest

import packages.biwenger_tools.bot.config as cfg
from packages.biwenger_tools.bot.app import app

_VALID_SECRET = "test-secret"
_VALID_CHAT = "111222333"
_API_URL = "https://biwenger-api.example.run.app"


@pytest.fixture(autouse=True)
def patch_config():
    """Set known config values for every test."""
    cfg.TELEGRAM_WEBHOOK_SECRET = _VALID_SECRET
    cfg.TELEGRAM_CHAT_ID = _VALID_CHAT
    cfg.TELEGRAM_BOT_TOKEN = "test-token"
    cfg.BIWENGER_API_URL = _API_URL
    yield


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _update(chat_id, text):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


def _post(client, body, secret=_VALID_SECRET):
    return client.post(
        "/telegram/webhook",
        json=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": secret},
    )


# --- Auth ---


def test_wrong_secret_returns_401(client):
    resp = _post(client, _update(_VALID_CHAT, "/analizar"), secret="wrong")
    assert resp.status_code == 401


def test_correct_secret_returns_200(client):
    with patch("packages.biwenger_tools.bot.app.api_client.call_api"):
        resp = _post(client, _update(_VALID_CHAT, "/analizar"))
    assert resp.status_code == 200


# --- Chat filter ---


def test_wrong_chat_id_is_silently_ignored(client):
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _update("999999", "/analizar"))
    assert resp.status_code == 200
    mock_call.assert_not_called()


# --- Command → api route mapping ---


@pytest.mark.parametrize(
    "command,path,method",
    [
        ("/analizar", "/teams", "GET"),
        ("/myTeam", "/teams/mine", "GET"),
        ("/myteam", "/teams/mine", "GET"),
        ("/mercado", "/market", "GET"),
        ("/alinear", "/lineups/auto-pick", "POST"),
        ("/recomendar", "/budget/recommendations", "GET"),
    ],
)
def test_command_calls_correct_api_endpoint(client, command, path, method):
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _update(_VALID_CHAT, command))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(_API_URL, path, method=method)


def test_command_with_botname_suffix_calls_api(client):
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _update(_VALID_CHAT, "/analizar@biwenger_tools_bot"))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(_API_URL, "/teams", method="GET")


def test_api_call_failure_sends_error_message(client):
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api",
        side_effect=RuntimeError("permission denied"),
    ), patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/analizar"))
    assert resp.status_code == 200
    # first call = ACK, second call = error
    assert mock_send.call_count == 2
    error_text = mock_send.call_args_list[1].kwargs.get("text", "")
    assert "permission denied" in error_text


# --- /help, /version, unknown ---


def test_help_sends_message(client):
    with patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/help"))
    assert resp.status_code == 200
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs.get("chat_id") == _VALID_CHAT


def test_version_includes_bot_and_api(client):
    """`/version` includes the bot SHA and the api's /version response."""
    cfg.GIT_COMMIT = "abc1234"
    cfg.DEPLOY_TIME = "17/05/2026 14:00"
    api_meta = {
        "service": "biwenger-api",
        "commit": "def5678",
        "deploy_time": "18/05/2026 16:00",
    }
    with patch(
        "packages.biwenger_tools.bot.app.api_client.get_api_version",
        return_value=api_meta,
    ), patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/version"))
    assert resp.status_code == 200
    text = mock_send.call_args.kwargs.get("text", "")
    assert "abc1234" in text
    assert "17/05/2026 14:00" in text
    assert "def5678" in text
    assert "18/05/2026 16:00" in text


def test_version_tolerates_api_unreachable(client):
    """If biwenger-api /version fails, bot still reports its own version."""
    cfg.GIT_COMMIT = "abc1234"
    cfg.DEPLOY_TIME = "17/05/2026 14:00"
    with patch(
        "packages.biwenger_tools.bot.app.api_client.get_api_version",
        return_value=None,
    ), patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/version"))
    assert resp.status_code == 200
    text = mock_send.call_args.kwargs.get("text", "")
    assert "abc1234" in text
    assert "unreachable" in text


def test_unknown_command_is_ignored(client):
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/unknown"))
    assert resp.status_code == 200
    mock_call.assert_not_called()
    mock_send.assert_not_called()


def test_empty_body_does_not_crash(client):
    resp = client.post(
        "/telegram/webhook",
        data="",
        content_type="application/json",
        headers={"X-Telegram-Bot-Api-Secret-Token": _VALID_SECRET},
    )
    assert resp.status_code == 200
