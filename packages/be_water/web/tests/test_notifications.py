"""The Telegram notice sent when a water is saved from the add form."""

from unittest.mock import patch

from packages.be_water.web import notifications

_URL = "https://bewater.example/agua/font-nova"


def test_a_new_water_names_the_water_its_author_and_what_was_read():
    text = notifications.save_notice(
        notifications.NEW,
        water_name="Font Nova",
        nickname="jorgelillo",
        url=_URL,
        minerals=7,
        label_verified=5,
    )
    assert "🆕" in text
    assert "<b>Font Nova</b>" in text and "<b>jorgelillo</b>" in text
    assert "7 minerales" in text and "5 leídos de la etiqueta" in text
    assert _URL in text


def test_an_update_and_a_history_entry_say_which_they_are():
    updated = notifications.save_notice(
        notifications.UPDATED,
        water_name="Bezoya",
        nickname="bea",
        url=_URL,
        analysis_date="2025-02",
    )
    history = notifications.save_notice(
        notifications.HISTORY,
        water_name="Bezoya",
        nickname="bea",
        url=_URL,
        analysis_date="2024-01",
    )
    assert "♻️" in updated and "actualizada" in updated and "2025-02" in updated
    assert "📚" in history and "historial" in history and "2024-01" in history


def test_user_text_cannot_break_the_html_the_message_is_sent_as():
    """A name with `<` or `&` would make Telegram reject the whole message."""
    text = notifications.save_notice(
        notifications.NEW, water_name="A&B <Agua>", nickname="x<y", url=_URL
    )
    assert "A&amp;B &lt;Agua&gt;" in text and "x&lt;y" in text


def test_nothing_is_sent_without_a_configured_chat():
    with patch.object(notifications.config, "TELEGRAM_BOT_TOKEN", ""), patch.object(
        notifications, "send_telegram_message"
    ) as send:
        notifications.notify_save(
            notifications.NEW, water_name="X", nickname="y", url=_URL
        )
    send.assert_not_called()


def test_a_failed_delivery_is_logged_not_raised():
    """The save already happened; a Telegram outage must not turn it into a 500."""
    with patch.object(notifications.config, "TELEGRAM_BOT_TOKEN", "t"), patch.object(
        notifications.config, "TELEGRAM_CHAT_ID", "1"
    ), patch.object(notifications, "send_telegram_message", return_value=False) as send:
        notifications.notify_save(
            notifications.NEW, water_name="X", nickname="y", url=_URL
        )
    send.assert_called_once()
