"""Chuck Norris Jokes Telegram bot — webhook handler."""

import os

import requests
from flask import Flask, render_template, request

from core.sdk.telegram import (
    extract_webhook_update,
    parse_command,
    send_telegram_message,
    validate_webhook_secret,
)
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


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/telegram/webhook", methods=["POST"])
def webhook():
    if not validate_webhook_secret(request, config.TELEGRAM_WEBHOOK_SECRET):
        logger.warning(
            "Webhook: invalid secret token",
            extra={
                "remote_addr": request.remote_addr,
                "user_agent": request.headers.get("User-Agent", ""),
            },
        )
        return "", 401

    chat_id, text = extract_webhook_update(request)
    if not chat_id or not text:
        return "", 200

    cmd = parse_command(text)

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
