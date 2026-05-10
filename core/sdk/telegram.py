from typing import Any

import requests

from core.utils import get_logger

logger = get_logger(__name__)

TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_SET_COMMANDS_URL = "https://api.telegram.org/bot{token}/setMyCommands"
TELEGRAM_SET_MENU_BUTTON_URL = "https://api.telegram.org/bot{token}/setChatMenuButton"


def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
) -> None:
    """Sends a text message to a Telegram chat via the Bot API.

    Truncates messages over 4096 chars (the Telegram limit). For long content
    that needs splitting, do the splitting at the call site so each chunk
    forms a coherent unit.
    """
    if len(text) > 4096:
        logger.warning(
            "Telegram message exceeds 4096 chars — truncating.",
            extra={"length": len(text)},
        )
        text = text[:4093] + "..."

    url = TELEGRAM_SEND_MESSAGE_URL.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        logger.info("Telegram message sent.", extra={"chars": len(text)})
    except Exception as e:
        logger.error("Failed to send Telegram message.", extra={"error": str(e)})


def send_telegram_photo(
    bot_token: str,
    chat_id: str,
    image_bytes: bytes,
    caption: str = "",
) -> None:
    """Sends a PNG image to a Telegram chat via sendPhoto."""
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"photo": ("image.png", image_bytes, "image/png")},
            timeout=30,
        )
        response.raise_for_status()
        logger.info("Telegram photo sent.", extra={"caption": caption[:40]})
    except Exception as e:
        logger.error("Failed to send Telegram photo.", extra={"error": str(e)})


def register_bot_commands(bot_token: str, commands: list[dict]) -> None:
    """Registers bot commands so they appear in the Telegram '/' menu.

    Each entry in `commands` must have 'command' (lowercase, no slash)
    and 'description' keys.
    """
    url = TELEGRAM_SET_COMMANDS_URL.format(token=bot_token)
    try:
        response = requests.post(url, json={"commands": commands}, timeout=15)
        response.raise_for_status()
        logger.info("Bot commands registered.", extra={"count": len(commands)})
    except Exception as e:
        logger.error("Failed to register bot commands.", extra={"error": str(e)})


def set_commands_menu_button(bot_token: str) -> None:
    """Sets the bot's menu button to show the registered command list."""
    url = TELEGRAM_SET_MENU_BUTTON_URL.format(token=bot_token)
    try:
        response = requests.post(
            url, json={"menu_button": {"type": "commands"}}, timeout=15
        )
        response.raise_for_status()
        logger.info("Menu button set to 'commands'.")
    except Exception as e:
        logger.error("Failed to set menu button.", extra={"error": str(e)})


def parse_command(text: str) -> str:
    """Extract the bare command from a Telegram message text.

    '/analizar@bot arg' → '/analizar'
    '/HELP' → '/help'
    '' → ''
    """
    return text.lower().split()[0].split("@")[0] if text.strip() else ""


def extract_webhook_update(request: Any) -> tuple[str, str]:
    """Extract (chat_id, text) from a Flask webhook POST request body.

    Returns ('', '') for empty or malformed bodies.
    """
    body = request.get_json(silent=True) or {}
    message = body.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()
    return chat_id, text


def validate_webhook_secret(request: Any, expected: str) -> bool:
    """Return True if the X-Telegram-Bot-Api-Secret-Token header matches."""
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    return received == expected
