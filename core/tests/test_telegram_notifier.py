import requests_mock
from unittest.mock import patch, mock_open

from core.sdk.telegram import send_telegram_notification

TEST_API_URL = "https://api.telegram.org/bot{token}/sendDocument"
TEST_BOT_TOKEN = "test_bot_token"
TEST_CHAT_ID = "123456789"
TEST_CAPTION = "Test notification"
TEST_FILEPATH = "/path/to/test_file.txt"


def test_send_telegram_notification_success(caplog):
    """Notification is sent successfully and success is logged."""
    with requests_mock.Mocker() as m:
        m.post(
            TEST_API_URL.format(token=TEST_BOT_TOKEN),
            json={"ok": True},
            status_code=200,
        )

        with patch("builtins.open", mock_open(read_data=b"file content")):
            with patch("os.path.basename", return_value="test_file.txt"):
                send_telegram_notification(
                    TEST_API_URL,
                    TEST_BOT_TOKEN,
                    TEST_CHAT_ID,
                    TEST_CAPTION,
                    TEST_FILEPATH,
                )

        assert any("sent successfully" in r.message for r in caplog.records)
        assert m.called_once
        assert m.last_request.url == TEST_API_URL.format(token=TEST_BOT_TOKEN)
        assert "chat_id" in m.last_request.text


def test_send_telegram_notification_failure_api(caplog):
    """API error is handled and logged as an error."""
    with requests_mock.Mocker() as m:
        m.post(TEST_API_URL.format(token=TEST_BOT_TOKEN), status_code=404)

        with patch("builtins.open", mock_open(read_data=b"file content")):
            with patch("os.path.basename", return_value="test_file.txt"):
                send_telegram_notification(
                    TEST_API_URL,
                    TEST_BOT_TOKEN,
                    TEST_CHAT_ID,
                    TEST_CAPTION,
                    TEST_FILEPATH,
                )

    assert any("Failed to send" in r.message for r in caplog.records)


def test_send_telegram_notification_failure_file(caplog):
    """Missing file error is handled and logged as an error."""
    with requests_mock.Mocker() as m:
        send_telegram_notification(
            TEST_API_URL,
            TEST_BOT_TOKEN,
            TEST_CHAT_ID,
            TEST_CAPTION,
            "/non/existent/file.txt",
        )

    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert error_records
    assert any("No such file or directory" in r.getMessage() for r in error_records)
