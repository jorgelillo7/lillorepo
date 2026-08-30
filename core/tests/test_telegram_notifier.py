from unittest.mock import MagicMock

import pytest
import requests
import requests_mock

from core.sdk.telegram import (
    TELEGRAM_FILE_DOWNLOAD_URL,
    TELEGRAM_GET_FILE_URL,
    TELEGRAM_SEND_MESSAGE_URL,
    TELEGRAM_SET_COMMANDS_URL,
    TELEGRAM_SET_MENU_BUTTON_URL,
    configure_bot_commands,
    download_telegram_file,
    extract_webhook_callback,
    extract_webhook_media,
    extract_webhook_update,
    parse_command,
    register_bot_commands,
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

        ok = send_telegram_message(TEST_BOT_TOKEN, TEST_CHAT_ID, "hello <b>world</b>")

        assert ok is True
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


def test_send_telegram_message_returns_false_and_logs_on_api_failure(caplog):
    """4xx/5xx must surface as `return False` (not just a log line) so
    callers can decide whether to swallow or re-raise. Auto-bid uses
    this to bubble HTML-parse 400s up to the bot as an actionable 500."""
    with requests_mock.Mocker() as m:
        m.post(TELEGRAM_SEND_MESSAGE_URL.format(token=TEST_BOT_TOKEN), status_code=500)
        ok = send_telegram_message(TEST_BOT_TOKEN, TEST_CHAT_ID, "hi")
        assert ok is False
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
    req = _mock_json_request(
        {
            "message": {
                "chat": {"id": 42},
                "text": "/help",
                "from": {"id": 999},
            }
        }
    )
    chat_id, text, user_id = extract_webhook_update(req)
    assert chat_id == "42"
    assert text == "/help"
    assert user_id == "999"


def test_extract_webhook_update_empty_body():
    req = MagicMock()
    req.get_json = MagicMock(return_value=None)
    chat_id, text, user_id = extract_webhook_update(req)
    assert chat_id == ""
    assert text == ""
    assert user_id == ""


def test_extract_webhook_update_strips_text_whitespace():
    req = _mock_json_request({"message": {"chat": {"id": 1}, "text": "  /random  "}})
    _, text, _user_id = extract_webhook_update(req)
    assert text == "/random"


def test_extract_webhook_update_no_text_key():
    req = _mock_json_request({"message": {"chat": {"id": 1}}})
    _, text, _user_id = extract_webhook_update(req)
    assert text == ""


def test_extract_webhook_update_no_from_key():
    """Telegram service messages (e.g. a user added to the group) carry a
    chat id but no `from`/`text` — must not raise."""
    req = _mock_json_request({"message": {"chat": {"id": 1}}})
    chat_id, text, user_id = extract_webhook_update(req)
    assert chat_id == "1"
    assert text == ""
    assert user_id == ""


# --- register_bot_commands / configure_bot_commands scope ---

TEST_COMMANDS = [{"command": "help", "description": "Show help"}]


def test_register_bot_commands_without_scope_omits_scope_field():
    with requests_mock.Mocker() as m:
        m.post(
            TELEGRAM_SET_COMMANDS_URL.format(token=TEST_BOT_TOKEN), json={"ok": True}
        )
        register_bot_commands(TEST_BOT_TOKEN, TEST_COMMANDS)
        body = m.last_request.json()
        assert "scope" not in body


def test_register_bot_commands_with_scope_sends_it():
    scope = {"type": "chat", "chat_id": TEST_CHAT_ID}
    with requests_mock.Mocker() as m:
        m.post(
            TELEGRAM_SET_COMMANDS_URL.format(token=TEST_BOT_TOKEN), json={"ok": True}
        )
        register_bot_commands(TEST_BOT_TOKEN, TEST_COMMANDS, scope=scope)
        body = m.last_request.json()
        assert body["scope"] == scope


def test_configure_bot_commands_without_scope_resets_menu_button():
    with requests_mock.Mocker() as m:
        m.post(
            TELEGRAM_SET_COMMANDS_URL.format(token=TEST_BOT_TOKEN), json={"ok": True}
        )
        m.post(
            TELEGRAM_SET_MENU_BUTTON_URL.format(token=TEST_BOT_TOKEN), json={"ok": True}
        )
        configure_bot_commands(TEST_BOT_TOKEN, TEST_COMMANDS)
        menu_calls = [
            r
            for r in m.request_history
            if r.url == TELEGRAM_SET_MENU_BUTTON_URL.format(token=TEST_BOT_TOKEN)
        ]
        assert len(menu_calls) == 1


def test_configure_bot_commands_with_scope_skips_menu_button_reset():
    scope = {"type": "chat", "chat_id": TEST_CHAT_ID}
    with requests_mock.Mocker() as m:
        m.post(
            TELEGRAM_SET_COMMANDS_URL.format(token=TEST_BOT_TOKEN), json={"ok": True}
        )
        m.post(
            TELEGRAM_SET_MENU_BUTTON_URL.format(token=TEST_BOT_TOKEN), json={"ok": True}
        )
        configure_bot_commands(TEST_BOT_TOKEN, TEST_COMMANDS, scope=scope)
        body = m.request_history[0].json()
        assert body["scope"] == scope
        menu_calls = [
            r
            for r in m.request_history
            if r.url == TELEGRAM_SET_MENU_BUTTON_URL.format(token=TEST_BOT_TOKEN)
        ]
        assert len(menu_calls) == 0


# --- extract_webhook_callback ---


def test_extract_webhook_callback_carries_the_tapped_message_text():
    """The body of the message the button sat under. Telegram always sends
    it and it was being dropped, which is why a decision confirmation could
    only quote an id — the offer's own text was one field away."""
    req = _mock_json_request(
        {
            "callback_query": {
                "id": "cb-1",
                "data": "o:a:12345",
                "message": {
                    "chat": {"id": 42},
                    "message_id": 7,
                    "text": "📥 Oferta entrante\nJugador: Neto (MED)",
                },
            }
        }
    )
    cb = extract_webhook_callback(req)
    assert cb["data"] == "o:a:12345"
    assert cb["message_id"] == 7
    assert "Neto (MED)" in cb["text"]


def test_extract_webhook_callback_defaults_the_text_when_absent():
    """A media message has no `text`; callers must get "" rather than None."""
    req = _mock_json_request(
        {
            "callback_query": {
                "id": "cb-1",
                "data": "o:i:1",
                "message": {"chat": {"id": 42}, "message_id": 7},
            }
        }
    )
    assert extract_webhook_callback(req)["text"] == ""


def test_extract_webhook_callback_returns_none_for_a_plain_message():
    assert extract_webhook_callback(_mock_json_request({"message": {}})) is None


# --- extract_webhook_media ---


def _media_request(message: dict) -> MagicMock:
    return _mock_json_request({"update_id": 1, "message": message})


def test_extract_webhook_media_prefers_the_document():
    """A document keeps the original bytes; the `photo` Telegram builds beside
    it is the recompressed copy, unreadable for a newspaper page."""
    req = _media_request(
        {
            "chat": {"id": 7},
            "from": {"id": 9},
            "caption": "  2026-08-14 Titular  ",
            "document": {"file_id": "doc-1", "mime_type": "image/jpeg"},
            "photo": [{"file_id": "small"}, {"file_id": "big"}],
        }
    )

    media = extract_webhook_media(req)

    assert media == {
        "chat_id": "7",
        "user_id": "9",
        "file_id": "doc-1",
        "caption": "2026-08-14 Titular",
        "kind": "document",
    }


def test_extract_webhook_media_takes_the_largest_photo():
    req = _media_request(
        {
            "chat": {"id": 7},
            "photo": [{"file_id": "s"}, {"file_id": "m"}, {"file_id": "l"}],
        }
    )

    media = extract_webhook_media(req)

    assert media["file_id"] == "l"
    assert media["kind"] == "photo"
    assert media["caption"] == ""


def test_extract_webhook_media_ignores_non_image_documents():
    """A PDF or a CSV dropped in the chat must fall through to the text path."""
    req = _media_request(
        {"chat": {"id": 7}, "document": {"file_id": "d", "mime_type": "text/csv"}}
    )

    assert extract_webhook_media(req) is None


def test_extract_webhook_media_ignores_text_updates():
    req = _media_request({"chat": {"id": 7}, "text": "/mercado"})

    assert extract_webhook_media(req) is None


# --- download_telegram_file ---


def test_download_telegram_file_resolves_path_then_fetches():
    with requests_mock.Mocker() as m:
        m.get(
            TELEGRAM_GET_FILE_URL.format(token=TEST_BOT_TOKEN),
            json={"ok": True, "result": {"file_path": "photos/f.jpg"}},
        )
        m.get(
            TELEGRAM_FILE_DOWNLOAD_URL.format(
                token=TEST_BOT_TOKEN, path="photos/f.jpg"
            ),
            content=b"\xff\xd8\xffbytes",
        )

        assert download_telegram_file(TEST_BOT_TOKEN, "file-1") == b"\xff\xd8\xffbytes"


def test_download_telegram_file_raises_when_getfile_refuses():
    """getFile 400s on anything over 20 MB — the bytes are simply unreachable,
    so the caller has to tell the operator rather than retry."""
    with requests_mock.Mocker() as m:
        m.get(
            TELEGRAM_GET_FILE_URL.format(token=TEST_BOT_TOKEN),
            json={"ok": False, "description": "file is too big"},
            status_code=400,
        )

        with pytest.raises(requests.RequestException):
            download_telegram_file(TEST_BOT_TOKEN, "huge")
