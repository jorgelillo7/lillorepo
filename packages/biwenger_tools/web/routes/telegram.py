"""Telegram webhook handler — single-tenant bot for the Lloros league."""

from flask import Blueprint, Response, abort, request

from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.biwenger_tools.teams_analyzer.teams_analyzer import main as run_analyzer
from packages.biwenger_tools.web import config

logger = get_logger(__name__)

bp = Blueprint("telegram", __name__)

_HELP_TEXT = (
    "Available commands:\n"
    "/analizar — run squad & market analysis\n"
    "/help — show this message"
)


def _parse_command(text: str) -> str:
    """Return the base command (strips @botname suffix), or '' if not a command."""
    if not text.startswith("/"):
        return ""
    return text.split("@")[0].split()[0]


@bp.route("/telegram/webhook", methods=["POST"])
def webhook() -> Response:
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not config.TELEGRAM_WEBHOOK_SECRET or token != config.TELEGRAM_WEBHOOK_SECRET:
        abort(401)

    update = request.get_json(silent=True) or {}
    message = update.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()

    if chat_id != str(config.TELEGRAM_CHAT_ID):
        return "", 200

    command = _parse_command(text)

    if command == "/analizar":
        logger.info("Telegram /analizar — starting analysis.")
        run_analyzer()
    elif command == "/help":
        send_telegram_message(
            config.TELEGRAM_BOT_TOKEN,
            config.TELEGRAM_CHAT_ID,
            _HELP_TEXT,
        )

    return "", 200
