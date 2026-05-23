"""Biwenger bot service — handles Telegram webhook and calls biwenger-api.

Two kinds of updates land on the webhook:

1. **Text commands** (`/menu`, `/analizar`, etc.). `/analizar` opens the
   manager picker; the rest dispatch directly to biwenger-api.
2. **Inline-keyboard taps** (callback_query). `menu:<action>` rows
   either dispatch the action (mercado, alinear, …) or — for analizar —
   answer with the manager picker. `analizar:<id|all>` taps run the
   teams endpoint with the selected filter.

Heavy work always runs synchronously against biwenger-api; the bot only
acknowledges the tap, edits the picker into a "processing…" message and
lets the api post the results.
"""

import os

from flask import Flask, request

from core.sdk.telegram import (
    answer_callback_query,
    edit_message_text,
    extract_webhook_callback,
    extract_webhook_update,
    parse_command,
    send_telegram_message,
    validate_webhook_secret,
)
from core.utils import get_logger
from packages.biwenger_tools.bot import api_client, config, menu

logger = get_logger(__name__)

app = Flask(__name__)

_HELP_TEXT = (
    "<b>Biwenger Bot</b>\n\n"
    "/menu — Menú visual con botones (recomendado)\n"
    "/analizar — Análisis (te pregunta a quién)\n"
    "/mercado — Solo el mercado\n"
    "/alinear — Aplica la mejor alineación posible\n"
    "/preview — Previsualiza la alineación sin aplicarla\n"
    "/recomendar — Qué fichar si me clausulan (top 3 por posición)\n"
    "/pujar — Lanza el auto-bid del mercado diario por tiers\n"
    "/scrapper — Lanza el scraper a demanda (te avisa al acabar)\n"
    "/version — Versión desplegada del bot y de la API\n"
    "/help — Muestra este mensaje"
)

# Map main-menu action key → (api path, http method, query params).
# `analizar` is special because it opens the manager picker before
# hitting any endpoint. `alinear_dry` mirrors `alinear` but with
# `?dry_run=1` so the api previews the lineup without doing the PUT.
_ACTION_ROUTES: dict[str, tuple[str, str, dict | None]] = {
    "mercado": ("/market", "GET", None),
    "alinear": ("/lineups/auto-pick", "POST", None),
    "alinear_dry": ("/lineups/auto-pick", "POST", {"dry_run": "1"}),
    "recomendar": ("/budget/recommendations", "GET", None),
    "pujar": ("/market/auto-bid", "POST", None),
    "scrapper": ("/scraper/trigger", "POST", None),
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


def _send_menu() -> None:
    """Send the main inline-keyboard menu to the configured chat."""
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text="<b>¿Qué hacemos?</b>",
        reply_markup=menu.main_menu_keyboard(),
    )


def _send_manager_picker() -> None:
    """Ask biwenger-api for the manager list and post the picker keyboard.

    Hitting `/managers` on every tap is fine — it's a single Biwenger
    league call (well under a second). No caching keeps the flow stateless.
    """
    managers = (
        api_client.list_managers(config.BIWENGER_API_URL)
        if config.BIWENGER_API_URL
        else None
    )
    if not managers:
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            text="❌ No pude cargar la lista de managers. Vuelve a intentarlo.",
        )
        return
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text="<b>📊 Analizar — ¿a quién?</b>",
        reply_markup=menu.managers_keyboard(managers),
    )


def _dispatch_action(action_key: str, label: str) -> None:
    """Send "procesando…" and fire the matching api endpoint."""
    path, method, params = _ACTION_ROUTES[action_key]
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text=f"⏳ <b>{label}</b> — procesando…",
    )
    try:
        api_client.call_api(config.BIWENGER_API_URL, path, method=method, params=params)
    except Exception as exc:
        logger.error(
            "Webhook: api call failed",
            extra={"action": action_key, "error": str(exc)},
        )
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            text=f"❌ Error al ejecutar <b>{label}</b>: <code>{exc}</code>",
        )


def _run_analizar(manager_value: str, edit_into: tuple[str, int] | None) -> None:
    """Call `/teams` with the selected manager filter.

    `edit_into` is a `(chat_id, message_id)` of the picker that triggered
    this — when present, the picker is replaced with a "procesando…" line
    so the chat history stays clean. `manager_value` is the raw callback
    payload: either a digit string (manager id) or `"all"`.
    """
    if manager_value == "all":
        params = None
        label = "Analizar — TODOS"
    else:
        params = {"manager": manager_value}
        label = f"Analizar — manager {manager_value}"

    status_text = f"⏳ <b>{label}</b> — procesando…"
    if edit_into is not None:
        chat_id, message_id = edit_into
        edit_message_text(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=chat_id,
            message_id=message_id,
            text=status_text,
        )
    else:
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            text=status_text,
        )

    try:
        api_client.call_api(
            config.BIWENGER_API_URL, "/teams", method="GET", params=params
        )
    except Exception as exc:
        logger.error(
            "Webhook: /teams call failed",
            extra={"manager": manager_value, "error": str(exc)},
        )
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            text=f"❌ Error al ejecutar <b>{label}</b>: <code>{exc}</code>",
        )


def _handle_callback(cb: dict) -> None:
    """Dispatch on the callback_data prefix.

    `menu:analizar` opens the manager picker (a second keyboard).
    `menu:<other>` fires the matching api endpoint.
    `analizar:<id|all>` runs `/teams` with the filter.
    """
    answer_callback_query(config.TELEGRAM_BOT_TOKEN, cb["id"])
    data = cb.get("data", "")
    if ":" not in data:
        logger.info("Webhook: unknown callback_data", extra={"data": data})
        return
    prefix, value = data.split(":", 1)

    if prefix == "menu":
        if value == "analizar":
            _send_manager_picker()
            return
        if value in _ACTION_ROUTES:
            label = next(lbl for key, lbl in menu.MAIN_MENU_ACTIONS if key == value)
            _dispatch_action(value, label)
            return
        logger.info("Webhook: unknown menu action", extra={"value": value})
        return

    if prefix == "analizar":
        edit_into = (cb["chat_id"], cb["message_id"]) if cb.get("message_id") else None
        _run_analizar(value, edit_into)
        return

    logger.info("Webhook: unhandled callback prefix", extra={"prefix": prefix})


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

    # Inline-keyboard tap first — callback updates carry no `message.text`.
    cb = extract_webhook_callback(request)
    if cb is not None:
        if cb["chat_id"] != config.TELEGRAM_CHAT_ID:
            logger.info(
                "Webhook: ignoring callback from unknown chat",
                extra={"chat_id": cb["chat_id"]},
            )
            return "", 200
        _handle_callback(cb)
        return "", 200

    chat_id, text = extract_webhook_update(request)
    if chat_id != config.TELEGRAM_CHAT_ID:
        logger.info(
            "Webhook: ignoring message from unknown chat",
            extra={"chat_id": chat_id},
        )
        return "", 200

    cmd = parse_command(text)

    if cmd in ("/menu", "/start"):
        logger.info("Webhook: %s received", cmd)
        _send_menu()
    elif cmd == "/analizar":
        logger.info("Webhook: /analizar received — sending picker")
        _send_manager_picker()
    elif cmd == "/mercado":
        _dispatch_action("mercado", "🛒 Mercado")
    elif cmd == "/alinear":
        _dispatch_action("alinear", "📋 Alinear")
    elif cmd == "/preview":
        _dispatch_action("alinear_dry", "👀 Preview alineación")
    elif cmd == "/recomendar":
        _dispatch_action("recomendar", "💡 Recomendar")
    elif cmd == "/pujar":
        _dispatch_action("pujar", "💸 Pujar")
    elif cmd == "/scrapper":
        _dispatch_action("scrapper", "🧹 Scraper")
    elif cmd == "/help":
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=config.TELEGRAM_CHAT_ID,
            text=_HELP_TEXT,
        )
    elif cmd == "/version":
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
