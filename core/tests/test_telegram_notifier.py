import requests_mock

from core.sdk.telegram import TELEGRAM_SEND_MESSAGE_URL, send_telegram_message

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
