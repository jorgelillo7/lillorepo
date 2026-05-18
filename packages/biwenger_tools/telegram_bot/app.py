"""Telegram bot service — handles webhook requests and calls biwenger-api."""

import os

from flask import Flask, request

from core.sdk.telegram import (
    extract_webhook_update,
    parse_command,
    send_telegram_message,
    validate_webhook_secret,
)
from core.utils import get_logger
from packages.biwenger_tools.telegram_bot import api_client, config

logger = get_logger(__name__)

app = Flask(__name__)

_HELP_TEXT = (
    "<b>Biwenger Bot</b>\n\n"
    "/analizar — Análisis completo (todos los equipos)\n"
    "/myteam — Análisis solo de mi equipo\n"
    "/mercado — Solo el mercado\n"
    "/alinear — Aplica la mejor alineación posible\n"
    "/recomendar — Qué fichar si me clausulan (top 3 por posición)\n"
    "/version — Versión desplegada del bot y de la API\n"
    "/help — Muestra este mensaje"
)

# Map Telegram command → (api path, http method).
_COMMAND_ROUTES = {
    "/analizar": ("/teams", "GET"),
    "/myteam": ("/teams/mine", "GET"),
    "/mercado": ("/market", "GET"),
    "/alinear": ("/lineups/auto-pick", "POST"),
    "/recomendar": ("/budget/recommendations", "GET"),
}


def _build_version_text() -> str:
    """Render /version showing bot + biwenger-api state."""
    bot_commit = config.GIT_COMMIT or "unknown"
    bot_time = config.DEPLOY_TIME or "—"
    api_meta = (
        api_client.get_api_version(config.BIWENGER_API_URL)
        if config.BIWENGER_API_URL
        else None
    )
    if api_meta:
        api_line = (
            f"  <code>{api_meta.get('commit', '?')}</code> · "
            f"{api_meta.get('deploy_time', '—')}"
        )
    else:
        api_line = "  (unreachable)"
    return (
        "<b>📦 Versiones desplegadas</b>\n\n"
        f"🤖 Bot service:\n  <code>{bot_commit}</code> · {bot_time}\n\n"
        f"⚙️ Biwenger API:\n{api_line}"
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

    if cmd in _COMMAND_ROUTES:
        path, method = _COMMAND_ROUTES[cmd]
        logger.info("Webhook: %s received — calling api %s %s", cmd, method, path)
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            text=f"⏳ <code>{cmd}</code> recibido, procesando…",
        )
        try:
            api_client.call_api(config.BIWENGER_API_URL, path, method=method)
        except Exception as exc:
            logger.error(
                "Webhook: api call failed",
                extra={"cmd": cmd, "error": str(exc)},
            )
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=config.TELEGRAM_CHAT_ID,
                text=f"❌ Error al ejecutar <code>{cmd}</code>: <code>{exc}</code>",
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
