"""Tests for the Chuck Norris bot webhook."""

import pytest
from unittest.mock import patch

import packages.chucknorris_bot.bot.config as cfg
from packages.chucknorris_bot.bot.app import app, _fetch_joke, _parse_command

_VALID_SECRET = "test-secret"


@pytest.fixture(autouse=True)
def patch_config():
    cfg.TELEGRAM_BOT_TOKEN = "test-token"
    cfg.TELEGRAM_WEBHOOK_SECRET = _VALID_SECRET
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
    resp = _post(client, _update("123", "/help"), secret="wrong")
    assert resp.status_code == 401


def test_correct_secret_returns_200(client):
    with patch("packages.chucknorris_bot.bot.app.send_telegram_message"):
        resp = _post(client, _update("123", "/help"))
    assert resp.status_code == 200


# --- Commands ---


def test_help_sends_message(client):
    with patch("packages.chucknorris_bot.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update("123", "/help"))
    assert resp.status_code == 200
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["chat_id"] == "123"


def test_start_sends_message(client):
    with patch("packages.chucknorris_bot.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update("123", "/start"))
    assert resp.status_code == 200
    mock_send.assert_called_once()


def test_random_fetches_and_sends(client):
    with patch(
        "packages.chucknorris_bot.bot.app._fetch_joke", return_value="A joke."
    ) as mock_fetch, patch(
        "packages.chucknorris_bot.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update("123", "/random"))
    assert resp.status_code == 200
    mock_fetch.assert_called_once_with()
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["text"] == "A joke."


@pytest.mark.parametrize("category", ["science", "food", "animal", "dev"])
def test_category_command_fetches_with_category(client, category):
    with patch(
        "packages.chucknorris_bot.bot.app._fetch_joke", return_value="A joke."
    ) as mock_fetch, patch("packages.chucknorris_bot.bot.app.send_telegram_message"):
        resp = _post(client, _update("123", f"/{category}"))
    assert resp.status_code == 200
    mock_fetch.assert_called_once_with(category)


def test_unknown_command_is_ignored(client):
    with patch("packages.chucknorris_bot.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update("123", "/unknown"))
    assert resp.status_code == 200
    mock_send.assert_not_called()


def test_command_with_botname_suffix_is_parsed(client):
    with patch("packages.chucknorris_bot.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update("123", "/help@chucknorris_bot"))
    assert resp.status_code == 200
    mock_send.assert_called_once()


def test_empty_body_does_not_crash(client):
    resp = client.post(
        "/telegram/webhook",
        data="",
        content_type="application/json",
        headers={"X-Telegram-Bot-Api-Secret-Token": _VALID_SECRET},
    )
    assert resp.status_code == 200


def test_message_without_text_is_ignored(client):
    body = {"update_id": 1, "message": {"chat": {"id": "123"}}}
    with patch("packages.chucknorris_bot.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, body)
    assert resp.status_code == 200
    mock_send.assert_not_called()


# --- _parse_command ---


def test_parse_command_strips_botname():
    assert _parse_command("/random@mybot") == "/random"


def test_parse_command_lowercase():
    assert _parse_command("/HELP") == "/help"


def test_parse_command_empty():
    assert _parse_command("") == ""


# --- _fetch_joke ---


def test_fetch_joke_returns_joke():
    with patch("packages.chucknorris_bot.bot.app.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = {
            "value": "Chuck Norris can divide by zero."
        }
        result = _fetch_joke()
    assert result == "Chuck Norris can divide by zero."


def test_fetch_joke_with_category_appends_param():
    with patch("packages.chucknorris_bot.bot.app.requests.get") as mock_get:
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json.return_value = {"value": "Science joke."}
        _fetch_joke("science")
    call_url = mock_get.call_args[0][0]
    assert "category=science" in call_url


def test_fetch_joke_handles_error():
    with patch(
        "packages.chucknorris_bot.bot.app.requests.get",
        side_effect=RuntimeError("timeout"),
    ):
        result = _fetch_joke()
    assert "Chuck Norris" in result
