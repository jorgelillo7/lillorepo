import os

import requests

from core.utils import get_logger

logger = get_logger(__name__)


def send_telegram_notification(
    api_url_template: str,
    bot_token: str,
    chat_id: str,
    caption: str,
    filepath: str,
) -> None:
    """
    Sends a file to a Telegram chat via the Bot API.
    The API URL template is injected to decouple from config.
    """
    logger.info("Sending Telegram notification...", extra={"filepath": filepath})
    url = api_url_template.format(token=bot_token)
    try:
        with open(filepath, "rb") as f:
            files = {"document": (os.path.basename(filepath), f)}
            data = {"chat_id": chat_id, "caption": caption}
            response = requests.post(url, data=data, files=files)
            response.raise_for_status()
        logger.info("Telegram notification sent successfully.")
    except Exception as e:
        logger.error("Failed to send Telegram notification.", extra={"error": str(e)})
