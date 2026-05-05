import io

import requests

from core.utils import get_logger

logger = get_logger(__name__)

TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_SEND_DOCUMENT_URL = "https://api.telegram.org/bot{token}/sendDocument"


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


def send_telegram_document(
    bot_token: str,
    chat_id: str,
    filename: str,
    data: bytes,
    caption: str = "",
) -> None:
    """Sends a file (CSV, PDF, …) to a Telegram chat via sendDocument."""
    url = TELEGRAM_SEND_DOCUMENT_URL.format(token=bot_token)
    try:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"document": (filename, io.BytesIO(data), "text/csv")},
            timeout=30,
        )
        response.raise_for_status()
        logger.info("Telegram document sent.", extra={"filename": filename})
    except Exception as e:
        logger.error(
            "Failed to send Telegram document.", extra={"error": str(e)}
        )
