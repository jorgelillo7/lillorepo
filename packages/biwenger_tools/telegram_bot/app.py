"""Telegram bot service — handles webhook requests and triggers Cloud Run Jobs."""

import os
from datetime import datetime

from flask import Flask, request

from core.constants import MADRID_TZ
from core.sdk.telegram import (
    extract_webhook_update,
    parse_command,
    send_telegram_message,
    validate_webhook_secret,
)
from core.utils import get_logger
from packages.biwenger_tools.telegram_bot import config, job_trigger

logger = get_logger(__name__)

app = Flask(__name__)

_HELP_TEXT = (
    "<b>Biwenger Bot</b>\n\n"
    "/analizar — Análisis completo (todos los equipos)\n"
    "/myteam — Análisis solo de mi equipo\n"
    "/mercado — Solo el mercado\n"
    "/alinear — Aplica la mejor alineación posible\n"
    "/version — Versión desplegada del bot y del job\n"
    "/help — Muestra este mensaje"
)

_JOB_MODES = {
    "/analizar": "all",
    "/myteam": "my_team",
    "/mercado": "market",
    "/alinear": "alinear",
}


def _format_madrid(iso_str: str | None) -> str:
    """Render an ISO-8601 UTC timestamp as `dd/MM/YYYY HH:mm` in Madrid time.

    The Cloud Run Jobs API returns `updateTime` as RFC3339 / ISO 8601 in UTC
    (e.g. `2026-05-17T13:25:20.461797Z`). We surface it next to the bot's own
    DEPLOY_TIME, which is already Madrid-localised by CI, so the two read at
    a glance instead of forcing the user to do timezone math.
    """
    if not iso_str:
        return "—"
    try:
        dt_utc = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt_utc.astimezone(MADRID_TZ).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return iso_str  # fall back to raw if the API ever returns an oddity


def _build_version_text() -> str:
    """Render the /version response showing bot + analyzer-job state."""
    bot_commit = config.GIT_COMMIT or "unknown"
    bot_time = config.DEPLOY_TIME or "—"
    job_time = _format_madrid(
        job_trigger.get_job_update_time(
            config.GCP_PROJECT_ID,
            config.CLOUD_RUN_REGION,
            config.CLOUD_RUN_JOB_NAME,
        )
    )
    return (
        "<b>📦 Versiones desplegadas</b>\n\n"
        f"🤖 Bot service:\n  <code>{bot_commit}</code> · {bot_time}\n\n"
        f"⚙️ Analyzer job ({config.CLOUD_RUN_JOB_NAME}):\n  updated {job_time}"
    )


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

    if chat_id != config.TELEGRAM_CHAT_ID:
        logger.info(
            "Webhook: ignoring message from unknown chat",
            extra={"chat_id": chat_id},
        )
        return "", 200

    cmd = parse_command(text)

    if cmd in _JOB_MODES:
        mode = _JOB_MODES[cmd]
        logger.info("Webhook: %s received — triggering job (%s)", cmd, mode)
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            text=f"⏳ <code>{cmd}</code> recibido, procesando…",
        )
        try:
            job_trigger.trigger_analyzer_job(
                config.GCP_PROJECT_ID,
                config.CLOUD_RUN_REGION,
                config.CLOUD_RUN_JOB_NAME,
                mode=mode,
            )
        except Exception as exc:
            logger.error(
                "Webhook: job trigger failed",
                extra={"cmd": cmd, "error": str(exc)},
            )
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=config.TELEGRAM_CHAT_ID,
                text=f"❌ Error al lanzar <code>{cmd}</code>: <code>{exc}</code>",
            )
    elif cmd == "/help":
        logger.info("Webhook: /help received")
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            text=_HELP_TEXT,
        )
    elif cmd == "/version":
        logger.info("Webhook: /version received")
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            text=_build_version_text(),
        )
    else:
        logger.info("Webhook: unknown command, ignoring", extra={"text": text[:50]})

    return "", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
