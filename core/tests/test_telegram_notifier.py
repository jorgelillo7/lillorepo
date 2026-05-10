from unittest.mock import MagicMock

import requests_mock

from core.sdk.telegram import (
    TELEGRAM_SEND_MESSAGE_URL,
    extract_webhook_update,
    parse_command,
    send_telegram_message,
    validate_webhook_secret,
)

TEST_BOT_TOKEN = "test_bot_token"
TEST_CHAT_ID = "123456789"


def test_send_telegram_message_success(caplog):
    with requests_mock.Mocker() as m:
        m.post(
            TELEGRAM_SEND_MESSAGE_URL.format(token=TEST_BOT_TOKEN),
            json={"ok": True},
            status_code=200,
        )

        send_telegram_message(TEST_BOT_TOKEN, TEST_CHAT_ID, "hello <b>world</b>")

        assert m.called_once
        body = m.last_request.json()
        assert body["chat_id"] == TEST_CHAT_ID
        assert body["text"] == "hello <b>world</b>"
        assert body["parse_mode"] == "HTML"
        assert body["disable_web_page_preview"] is True
        assert any("Telegram message sent" in r.message for r in caplog.records)


def test_send_telegram_message_truncates_long_text():
    long_text = "x" * 5000
    with requests_mock.Mocker() as m:
        m.post(
            TELEGRAM_SEND_MESSAGE_URL.format(token=TEST_BOT_TOKEN),
            json={"ok": True},
            status_code=200,
        )
        send_telegram_message(TEST_BOT_TOKEN, TEST_CHAT_ID, long_text)
        sent = m.last_request.json()["text"]
        assert len(sent) == 4096
        assert sent.endswith("...")


def test_send_telegram_message_logs_error_on_api_failure(caplog):
    with requests_mock.Mocker() as m:
        m.post(TELEGRAM_SEND_MESSAGE_URL.format(token=TEST_BOT_TOKEN), status_code=500)
        send_telegram_message(TEST_BOT_TOKEN, TEST_CHAT_ID, "hi")
        assert any(
            "Failed to send Telegram message" in r.message for r in caplog.records
        )


# --- parse_command ---


def test_parse_command_strips_botname():
    assert parse_command("/analizar@biwenger_bot") == "/analizar"


def test_parse_command_lowercases():
    assert parse_command("/HELP") == "/help"


def test_parse_command_strips_arguments():
    assert parse_command("/myteam foo bar") == "/myteam"


def test_parse_command_empty_string():
    assert parse_command("") == ""


def test_parse_command_whitespace_only():
    assert parse_command("   ") == ""


# --- validate_webhook_secret ---


def _mock_request(secret: str) -> MagicMock:
    req = MagicMock()
    req.headers.get = lambda key, default="": (
        secret if key == "X-Telegram-Bot-Api-Secret-Token" else default
    )
    return req


def test_validate_webhook_secret_match():
    assert validate_webhook_secret(_mock_request("abc123"), "abc123") is True


def test_validate_webhook_secret_mismatch():
    assert validate_webhook_secret(_mock_request("wrong"), "abc123") is False


def test_validate_webhook_secret_empty_header():
    assert validate_webhook_secret(_mock_request(""), "abc123") is False


# --- extract_webhook_update ---


def _mock_json_request(body: dict) -> MagicMock:
    req = MagicMock()
    req.get_json = MagicMock(return_value=body)
    return req


def test_extract_webhook_update_normal():
    req = _mock_json_request({"message": {"chat": {"id": 42}, "text": "/help"}})
    chat_id, text = extract_webhook_update(req)
    assert chat_id == "42"
    assert text == "/help"


def test_extract_webhook_update_empty_body():
    req = MagicMock()
    req.get_json = MagicMock(return_value=None)
    chat_id, text = extract_webhook_update(req)
    assert chat_id == ""
    assert text == ""


def test_extract_webhook_update_strips_text_whitespace():
    req = _mock_json_request({"message": {"chat": {"id": 1}, "text": "  /random  "}})
    _, text = extract_webhook_update(req)
    assert text == "/random"


def test_extract_webhook_update_no_text_key():
    req = _mock_json_request({"message": {"chat": {"id": 1}}})
    _, text = extract_webhook_update(req)
    assert text == ""
