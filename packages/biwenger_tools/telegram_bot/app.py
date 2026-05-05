"""Telegram bot service — handles webhook requests and triggers Cloud Run Jobs."""

import os

from flask import Flask, request

from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.biwenger_tools.telegram_bot import config, job_trigger

logger = get_logger(__name__)

app = Flask(__name__)

_HELP_TEXT = (
    "<b>Biwenger Bot</b>\n\n"
    "/analizar — Análisis completo (todos los equipos)\n"
    "/myTeam — Análisis solo de mi equipo\n"
    "/help — Muestra este mensaje"
)


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

    if chat_id != config.TELEGRAM_CHAT_ID:
        logger.info(
            "Webhook: ignoring message from unknown chat",
            extra={"chat_id": chat_id},
        )
        return "", 200

    if text.startswith("/analizar"):
        logger.info("Webhook: /analizar received — triggering job (all)")
        job_trigger.trigger_analyzer_job(
            config.GCP_PROJECT_ID,
            config.CLOUD_RUN_REGION,
            config.CLOUD_RUN_JOB_NAME,
            mode="all",
        )
    elif text.startswith("/myTeam"):
        logger.info("Webhook: /myTeam received — triggering job (my_team)")
        job_trigger.trigger_analyzer_job(
            config.GCP_PROJECT_ID,
            config.CLOUD_RUN_REGION,
            config.CLOUD_RUN_JOB_NAME,
            mode="my_team",
        )
    elif text.startswith("/help"):
        logger.info("Webhook: /help received")
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            text=_HELP_TEXT,
        )
    else:
        logger.info("Webhook: unknown command, ignoring", extra={"text": text[:50]})

    return "", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
