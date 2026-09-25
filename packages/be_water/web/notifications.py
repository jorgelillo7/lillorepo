"""Telegram notice for every water saved from the add form.

Best-effort: the save has already happened when this runs, so a missing chat
or a failed delivery is logged and never raised.
"""

import html
from typing import Optional

from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.be_water.web import config

logger = get_logger(__name__)

NEW = "new"
UPDATED = "updated"
HISTORY = "history"


def save_notice(
    event: str,
    *,
    water_name: str,
    nickname: str,
    url: str,
    analysis_date: Optional[str] = None,
    minerals: int = 0,
    label_verified: int = 0,
) -> str:
    """The HTML message for one save. User text is escaped: an unescaped `<`
    or `&` makes Telegram reject the whole message."""
    name = f"<b>{html.escape(water_name)}</b>"
    who = f"<b>{html.escape(nickname)}</b>"
    dated = f" · análisis {html.escape(analysis_date)}" if analysis_date else ""
    if event == NEW:
        head = f"🆕 {name} añadida por {who}"
    elif event == HISTORY:
        when = html.escape(analysis_date or "")
        head = f"📚 Análisis {when} de {name} añadido al historial por {who}"
        dated = ""
    else:
        head = f"♻️ {name} actualizada por {who}"
    lines = [head + dated]
    if minerals:
        lines.append(
            f"💧 {minerals} minerales · {label_verified} leídos de la etiqueta"
        )
    lines.append(url)
    return "\n".join(lines)


def notify_save(event: str, **details) -> None:
    """Send `save_notice` to the be_water chat, when one is configured."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    delivered = send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text=save_notice(event, **details),
    )
    if not delivered:
        logger.warning(
            "Save notice not delivered.",
            extra={"event": event, "water": details.get("water_name")},
        )
