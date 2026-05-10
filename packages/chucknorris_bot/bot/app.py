"""Chuck Norris Jokes Telegram bot — webhook handler."""

import os

import requests
from flask import Flask, request

from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.chucknorris_bot.bot import config

logger = get_logger(__name__)

app = Flask(__name__)

_CHUCK_API = "https://api.chucknorris.io/jokes/random"

_CATEGORIES = {"science", "food", "animal", "dev"}

_HELP_TEXT = (
    "<b>Chuck Norris Bot</b> 🤜\n\n"
    "Send me a category and I'll hit you with a fact:\n\n"
    "/random — random fact\n"
    "/science — science fact\n"
    "/food — food fact\n"
    "/animal — animal fact\n"
    "/dev — developer fact\n"
    "/help — show this message"
)


def _fetch_joke(category: str | None = None) -> str:
    url = _CHUCK_API
    if category:
        url += f"?category={category}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get("value", "Chuck Norris is speechless.")
    except Exception as exc:
        logger.error("Failed to fetch joke.", extra={"error": str(exc)})
        return "Chuck Norris broke the internet. Try again."


def _parse_command(text: str) -> str:
    return text.lower().split()[0].split("@")[0] if text.strip() else ""


@app.route("/telegram/webhook", methods=["POST"])
def webhook():
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != config.TELEGRAM_WEBHOOK_SECRET:
        logger.warning("Webhook: invalid secret token")
        return "", 401

    body = request.get_json(silent=True) or {}
    message = body.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return "", 200

    cmd = _parse_command(text)

    if cmd in ("/start", "/help"):
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=chat_id,
            text=_HELP_TEXT,
        )
    elif cmd == "/random":
        joke = _fetch_joke()
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=chat_id,
            text=joke,
        )
    elif cmd in {f"/{cat}" for cat in _CATEGORIES}:
        category = cmd[1:]
        joke = _fetch_joke(category)
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=chat_id,
            text=joke,
        )
    else:
        logger.info("Unknown command, ignoring.", extra={"text": text[:50]})

    return "", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
