"""Tests for the Telegram webhook handler."""

import pytest
from unittest.mock import MagicMock, patch

from packages.biwenger_tools.web.app import app
from packages.biwenger_tools.web import services

VALID_SECRET = "test-webhook-secret"
VALID_CHAT_ID = "-4825518712"


@pytest.fixture(autouse=True)
def mock_services():
    services.drive_service = MagicMock()
    services.sheets_service = MagicMock()
    yield
    services.drive_service = None
    services.sheets_service = None


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test_key"
    with app.test_client() as c:
        yield c


def _post(client, body, secret=VALID_SECRET):
    return client.post(
        "/telegram/webhook",
        json=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": secret},
    )


def _update(chat_id, text):
    return {"message": {"chat": {"id": int(chat_id)}, "text": text}}


@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_WEBHOOK_SECRET", VALID_SECRET)
@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_CHAT_ID", VALID_CHAT_ID)
def test_wrong_secret_returns_401(client):
    resp = _post(client, _update(VALID_CHAT_ID, "/analizar"), secret="bad-secret")
    assert resp.status_code == 401


@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_WEBHOOK_SECRET", VALID_SECRET)
@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_CHAT_ID", VALID_CHAT_ID)
@patch("packages.biwenger_tools.web.routes.telegram.run_analyzer")
def test_wrong_chat_id_ignored(mock_analyzer, client):
    resp = _post(client, _update("-9999999", "/analizar"))
    assert resp.status_code == 200
    assert resp.data == b""
    mock_analyzer.assert_not_called()


@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_WEBHOOK_SECRET", VALID_SECRET)
@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_CHAT_ID", VALID_CHAT_ID)
@patch("packages.biwenger_tools.web.routes.telegram.run_analyzer")
def test_analizar_triggers_analyzer(mock_analyzer, client):
    resp = _post(client, _update(VALID_CHAT_ID, "/analizar"))
    assert resp.status_code == 200
    mock_analyzer.assert_called_once()


@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_WEBHOOK_SECRET", VALID_SECRET)
@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_CHAT_ID", VALID_CHAT_ID)
@patch("packages.biwenger_tools.web.routes.telegram.run_analyzer")
def test_analizar_with_botname_suffix(mock_analyzer, client):
    resp = _post(client, _update(VALID_CHAT_ID, "/analizar@LlorosBot"))
    assert resp.status_code == 200
    mock_analyzer.assert_called_once()


@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_WEBHOOK_SECRET", VALID_SECRET)
@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_CHAT_ID", VALID_CHAT_ID)
@patch("packages.biwenger_tools.web.routes.telegram.send_telegram_message")
def test_help_sends_message(mock_send, client):
    resp = _post(client, _update(VALID_CHAT_ID, "/help"))
    assert resp.status_code == 200
    mock_send.assert_called_once()
    assert "/analizar" in mock_send.call_args[0][2]


@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_WEBHOOK_SECRET", VALID_SECRET)
@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_CHAT_ID", VALID_CHAT_ID)
@patch("packages.biwenger_tools.web.routes.telegram.run_analyzer")
def test_unknown_command_ignored(mock_analyzer, client):
    resp = _post(client, _update(VALID_CHAT_ID, "/alinear"))
    assert resp.status_code == 200
    mock_analyzer.assert_not_called()


@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_WEBHOOK_SECRET", VALID_SECRET)
@patch("packages.biwenger_tools.web.routes.telegram.config.TELEGRAM_CHAT_ID", VALID_CHAT_ID)
@patch("packages.biwenger_tools.web.routes.telegram.run_analyzer")
def test_plain_text_ignored(mock_analyzer, client):
    resp = _post(client, _update(VALID_CHAT_ID, "hello"))
    assert resp.status_code == 200
    mock_analyzer.assert_not_called()
