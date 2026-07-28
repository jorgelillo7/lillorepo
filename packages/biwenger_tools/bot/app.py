"""Biwenger bot service — handles Telegram webhook and calls biwenger-api.

Two chats are routed, each with its own command set:

1. **Owner private chat** (`config.TELEGRAM_CHAT_ID`) — the full admin
   surface: text commands (`/menu`, `/analizar`, etc.) and the matching
   inline-keyboard / reply-keyboard flows.
2. **Draft supergroup** (`config.TELEGRAM_DRAFT_CHAT_ID`) — only the
   draft commands (`/soy`, `/pick`, `/estado`, `/deshacer`, `/exportar`)
   and the `d:` disambiguation callback. The reply-keyboard label router
   and every admin command/callback prefix are unreachable from this
   chat. Any other chat is dropped silently (200, no reply).

The bot acknowledges every tap, edits the picker into a "procesando…"
message, then spawns a daemon thread to call biwenger-api so the webhook
returns 200 to Telegram immediately. Without that fire-and-forget pattern
a slow api call (e.g. /alinear on a 20+ player squad) blocks the gunicorn
worker past its 30 s timeout — Telegram retries the webhook and the user
sees the same "procesando…" line repeated 5-10 times.
"""

import html
import os
import threading

from flask import Flask, request

from core.sdk.telegram import (
    answer_callback_query,
    edit_message_reply_markup,
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
    "/ofertas — Lista ofertas entrantes con recomendación + botones\n"
    "/emergencia — Clausulazo de emergencia con confirmación (irreversible)\n"
    "/scrapper — Lanza el scraper a demanda (te avisa al acabar)\n"
    "/version — Versión desplegada del bot y de la API\n"
    "/help — Muestra este mensaje\n\n"
    "<i>Desktop:</i> si no ves el menú visual, pulsa el icono de "
    "teclado junto al input para desplegarlo."
)

_DRAFT_HELP_TEXT = (
    "<b>Draft Lloros League</b>\n\n"
    "/soy &lt;nombre&gt; — Vincula tu cuenta de Telegram con tu equipo\n"
    "/pick &lt;jugador&gt; — Ficha a un jugador en tu turno\n"
    "/estado — Turno actual, presupuestos y plantillas\n"
    "/deshacer — Revierte el último fichaje (admin)\n"
    "/exportar — Exporta todos los fichajes del draft"
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
    "emergencia": ("/emergency/clausulazo/preview", "POST", None),
    "ofertas": ("/offers/inbox", "POST", None),
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
    """Attach the persistent reply keyboard to the chat.

    Once Telegram receives this it pins the keyboard below the input
    field (`is_persistent: true`); subsequent bot messages don't need
    to re-attach it. Re-sending on demand (via `/menu` or `/start`) is
    how the user re-pins it if it ever got dismissed.
    """
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text="<b>¿Qué hacemos?</b>",
        reply_markup=menu.main_menu_reply_keyboard(),
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


def _run_in_background(fn, *args, **kwargs) -> None:
    """Spawn `fn` in a daemon thread so the webhook returns 200 immediately.

    Long-running api calls (notably /alinear with a 20+ player squad) used
    to block the gunicorn worker past its 30 s timeout — Telegram then
    retried the webhook and the user saw "procesando…" 5-10 times.
    Tests patch this helper to run sync so assertions stay deterministic.
    """
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


def _call_api_and_report(
    action_key: str,
    label: str,
    path: str,
    method: str,
    params: dict | None,
) -> None:
    """Call biwenger-api and post an HTML-escaped error on failure.

    Defensive HTML escape on `exc` — request body fragments and gcloud-style
    messages can contain `<`/`>`/`&` which would otherwise trigger a second
    Telegram 400 and leave the user with no feedback at all.
    """
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
            text=(
                f"❌ Error al ejecutar <b>{html.escape(label)}</b>: "
                f"<code>{html.escape(str(exc))}</code>"
            ),
        )


def _dispatch_action(action_key: str, label: str) -> None:
    """Send "procesando…" and fire the matching api endpoint in the background."""
    path, method, params = _ACTION_ROUTES[action_key]
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text=f"⏳ <b>{label}</b> — procesando…",
    )
    _run_in_background(_call_api_and_report, action_key, label, path, method, params)


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

    def _call_teams() -> None:
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

    _run_in_background(_call_teams)


def _run_emergencia_confirm(payload: str, edit_into: tuple[str, int] | None) -> None:
    """Tap on the "✅ Sí, clausular" button — fire `/emergency/execute`.

    `payload` is `c:<player_id>:<owner_id>:<amount>` (the `e:` prefix
    was already stripped). Validates the three ids parse to ints before
    calling the api so a malformed callback can't trigger a 400-loop.
    """
    parts = payload.split(":")
    if len(parts) != 4 or parts[0] != "c":
        logger.info("Webhook: malformed emergencia payload", extra={"payload": payload})
        return
    try:
        player_id, owner_id, amount = int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        logger.info(
            "Webhook: non-int in emergencia payload", extra={"payload": payload}
        )
        return

    # Strip the buttons off the preview so it can't be re-confirmed,
    # but keep the preview text intact for the chat history. The
    # "ejecutando…" / success messages arrive as fresh sends so the
    # original preview stays visible above them.
    if edit_into is not None:
        chat_id, message_id = edit_into
        edit_message_reply_markup(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup={"inline_keyboard": []},
        )
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text="⏳ <b>Emergencia</b> — ejecutando clausulazo…",
    )

    def _call_execute() -> None:
        try:
            api_client.call_api(
                config.BIWENGER_API_URL,
                "/emergency/clausulazo/execute",
                method="POST",
                params={
                    "player_id": str(player_id),
                    "owner_id": str(owner_id),
                    "amount": str(amount),
                },
            )
        except Exception as exc:
            logger.error(
                "Webhook: emergency execute failed",
                extra={"player_id": player_id, "error": str(exc)},
            )
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=config.TELEGRAM_CHAT_ID,
                text=(
                    f"❌ Error al ejecutar <b>Emergencia</b>: "
                    f"<code>{html.escape(str(exc))}</code>"
                ),
            )

    _run_in_background(_call_execute)


def _run_emergencia_cancel(edit_into: tuple[str, int] | None) -> None:
    """Tap on the "❌ No, cancelar" button — edit the preview to cancelled."""
    if edit_into is None:
        return
    chat_id, message_id = edit_into
    edit_message_text(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=chat_id,
        message_id=message_id,
        text="🚫 <b>Emergencia cancelada.</b>",
    )


def _run_emergencia_refine(params: dict, edit_into: tuple[str, int] | None) -> None:
    """Re-trigger /emergencia preview with a forced position/weakest flag.

    Fired by the selector buttons in the multi-clausulazo case
    (`e:p:<position>` and `e:m`). Strips the selector keyboard so it
    can't be re-tapped, then calls the preview endpoint with the user's
    choice — the api posts a fresh confirmation preview with Sí/No.
    """
    if edit_into is not None:
        chat_id, message_id = edit_into
        edit_message_reply_markup(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup={"inline_keyboard": []},
        )
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text="⏳ <b>Emergencia</b> — buscando objetivo…",
    )

    def _call_refine() -> None:
        try:
            api_client.call_api(
                config.BIWENGER_API_URL,
                "/emergency/clausulazo/preview",
                method="POST",
                params=params,
            )
        except Exception as exc:
            logger.error(
                "Webhook: emergency refine failed",
                extra={"params": params, "error": str(exc)},
            )
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=config.TELEGRAM_CHAT_ID,
                text=(
                    f"❌ Error al ejecutar <b>Emergencia</b>: "
                    f"<code>{html.escape(str(exc))}</code>"
                ),
            )

    _run_in_background(_call_refine)


def _run_offer_decision(decision_char: str, offer_id_str: str, edit_into) -> None:
    """Handle a tap on the ✅/❌/⏰ buttons under an `/ofertas` message.

    `decision_char` is the single-letter callback marker:
    - `a` → accept (PUT to api with decision="accepted")
    - `r` → reject (PUT with decision="rejected")
    - `i` → ignore (bot-side only: strip buttons, edit message text)

    `edit_into` is `(chat_id, message_id)` of the offer message so we
    can drop the keyboard once tapped — no double-confirm possible.
    """
    try:
        offer_id = int(offer_id_str)
    except ValueError:
        logger.info("Webhook: bad offer_id in callback", extra={"raw": offer_id_str})
        return

    if edit_into is not None:
        chat_id, message_id = edit_into
        edit_message_reply_markup(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup={"inline_keyboard": []},
        )

    if decision_char == "i":
        if edit_into is not None:
            chat_id, message_id = edit_into
            edit_message_text(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=chat_id,
                message_id=message_id,
                text=f"⏰ <b>Oferta ignorada</b> · id <code>{offer_id}</code>",
            )
        return

    decision = "accepted" if decision_char == "a" else "rejected"
    label = "Aceptar" if decision_char == "a" else "Rechazar"

    def _call_decide() -> None:
        try:
            api_client.call_api(
                config.BIWENGER_API_URL,
                "/offers/decide",
                method="POST",
                params={"offer_id": str(offer_id), "decision": decision},
            )
        except Exception as exc:
            logger.error(
                "Webhook: offer decision failed",
                extra={"offer_id": offer_id, "decision": decision, "error": str(exc)},
            )
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=config.TELEGRAM_CHAT_ID,
                text=(
                    f"❌ Error al {label.lower()} oferta "
                    f"<code>{offer_id}</code>: "
                    f"<code>{html.escape(str(exc))}</code>"
                ),
            )

    _run_in_background(_call_decide)


def _handle_callback(cb: dict) -> None:
    """Dispatch on the callback_data prefix.

    Inline-keyboard taps in scope:
    - `analizar:<id|all>` — manager picker for /analizar.
    - `e:c:<player_id>:<owner_id>:<amount>` — confirm /emergencia.
    - `e:p:<position_id>` — selector "reinforce this position".
    - `e:m` — selector "weakest line" fallback.
    - `e:n` — cancel /emergencia.
    - `o:a:<offer_id>` / `o:r:<offer_id>` / `o:i:<offer_id>` — accept /
      reject / ignore a received offer (the inbox flow).
    """
    data = cb.get("data", "")
    if ":" not in data:
        answer_callback_query(config.TELEGRAM_BOT_TOKEN, cb["id"])
        logger.info("Webhook: unknown callback_data", extra={"data": data})
        return
    prefix, value = data.split(":", 1)
    edit_into = (cb["chat_id"], cb["message_id"]) if cb.get("message_id") else None

    # Ack with a per-action toast where it adds UX value, otherwise plain.
    # The toast is the only feedback the user has between the tap and the
    # final confirmation message (which sits behind a cold-start of the
    # api + a Biwenger round-trip, ~8 s in the worst case).
    cb_id = cb["id"]
    if prefix == "o" and ":" in value and value.split(":", 1)[0] in ("a", "r"):
        marker = value.split(":", 1)[0]
        toast = "⏳ Aceptando…" if marker == "a" else "⏳ Rechazando…"
        answer_callback_query(config.TELEGRAM_BOT_TOKEN, cb_id, text=toast)
    else:
        answer_callback_query(config.TELEGRAM_BOT_TOKEN, cb_id)

    if prefix == "analizar":
        _run_analizar(value, edit_into)
        return

    if prefix == "e":
        if value == "n":
            _run_emergencia_cancel(edit_into)
        elif value == "m":
            _run_emergencia_refine({"force_weakest": "1"}, edit_into)
        elif value.startswith("p:"):
            _run_emergencia_refine(
                {"force_position": value.split(":", 1)[1]}, edit_into
            )
        else:
            _run_emergencia_confirm(value, edit_into)
        return

    if prefix == "o":
        # Expected shape: `o:a:<id>` / `o:r:<id>` / `o:i:<id>`.
        parts = value.split(":", 1)
        if len(parts) != 2 or parts[0] not in ("a", "r", "i"):
            logger.info("Webhook: malformed offer callback", extra={"value": value})
            return
        _run_offer_decision(parts[0], parts[1], edit_into)
        return

    logger.info("Webhook: unhandled callback prefix", extra={"prefix": prefix})


def _try_dispatch_label(text: str) -> bool:
    """Reply-keyboard taps arrive as plain text matching a button label.

    Returns True if the text matched a menu label and the action fired,
    False otherwise (so the caller can fall through to slash-command
    handling).
    """
    action_key = menu.LABEL_TO_ACTION.get(text)
    if action_key is None:
        return False
    if action_key == "analizar":
        _send_manager_picker()
    else:
        _dispatch_action(action_key, text)
    return True


def _handle_owner_message(text: str) -> None:
    """Full admin command set — owner private chat only, unchanged."""
    if _try_dispatch_label(text):
        return

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
    elif cmd == "/emergencia":
        _dispatch_action("emergencia", "🚨 Emergencia")
    elif cmd == "/ofertas":
        _dispatch_action("ofertas", "📥 Ofertas")
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


# --- Draft group -------------------------------------------------------------
#
# Reachable only from `config.TELEGRAM_DRAFT_CHAT_ID`. `biwenger-api` owns all
# draft state and player-name matching; every /draft/* response carries a
# ready-to-send Spanish `message` this layer just relays. Unlike the admin
# actions above (where biwenger-api posts to Telegram directly and the bot
# never reads the response body), the draft flow needs the parsed JSON back
# — an ambiguous /pick returns candidates to render as buttons, and every
# command's result text lives in the body, not pushed server-side.


def _command_arg(text: str) -> str:
    """Text after the command token, stripped. `''` if there is none."""
    parts = text.strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _call_draft_api(path: str, method: str, payload: dict | None) -> dict:
    """Call a `/draft/*` endpoint and return its parsed JSON body."""
    return api_client.call_api_json(config.BIWENGER_API_URL, path, method, payload)


def _draft_candidates_keyboard(requesting_user_id: str, candidates: list) -> dict:
    """Inline keyboard for an ambiguous `/pick` — one button per candidate.

    `callback_data` is `d:<requesting_user_id>:<player_id>` so the tap
    handler can both resolve the player and verify the tapper is the same
    user who ran `/pick` — nobody else can confirm someone else's pick.
    """
    rows = []
    for c in candidates:
        price = c.get("price", 0)
        label = f"{c.get('name', '?')} ({c.get('team', '?')}) · {price:,} EUR"
        rows.append(
            [
                {
                    "text": label,
                    "callback_data": f"d:{requesting_user_id}:{c.get('player_id')}",
                }
            ]
        )
    return {"inline_keyboard": rows}


def _run_draft_action(
    path: str, method: str, params: dict | None, chat_id: str, label: str
) -> None:
    """Call a `/draft/*` endpoint in the background and relay its `message`."""

    def _call() -> None:
        try:
            data = _call_draft_api(path, method, params)
        except Exception as exc:
            logger.error(
                "Webhook: draft api call failed",
                extra={"path": path, "error": str(exc)},
            )
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=chat_id,
                text=(
                    f"❌ Error al ejecutar <b>{html.escape(label)}</b>: "
                    f"<code>{html.escape(str(exc))}</code>"
                ),
            )
            return
        message = data.get("message", "")
        if message:
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN, chat_id=chat_id, text=message
            )

    _run_in_background(_call)


def _run_draft_pick(user_id: str, query: str, chat_id: str) -> None:
    """`/pick <jugador>` — resolve `query` against the draft pool.

    A clean match sends the api's confirmation message. An ambiguous match
    renders the candidates as an inline keyboard (`d:<user_id>:<player_id>`)
    instead — the user taps the right one to confirm.
    """

    def _call() -> None:
        try:
            data = _call_draft_api(
                "/draft/pick",
                "POST",
                {"telegram_user_id": user_id, "query": query},
            )
        except Exception as exc:
            logger.error(
                "Webhook: draft pick failed",
                extra={"user_id": user_id, "error": str(exc)},
            )
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=chat_id,
                text=(
                    f"❌ Error al ejecutar <b>Pick</b>: "
                    f"<code>{html.escape(str(exc))}</code>"
                ),
            )
            return

        message = data.get("message", "")
        if data.get("status") == "ambiguous":
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=chat_id,
                text=message,
                reply_markup=_draft_candidates_keyboard(
                    user_id, data.get("candidates", [])
                ),
            )
        elif message:
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN, chat_id=chat_id, text=message
            )

    _run_in_background(_call)


def _handle_draft_message(text: str, user_id: str) -> None:
    """Route a draft-group message straight to `parse_command`.

    Deliberately skips `_try_dispatch_label` — that router fires on plain
    text matching an admin menu label, which ordinary group chatter could
    collide with. Empty `text` (Telegram service messages, e.g. someone
    added to the group) falls through every branch below and is dropped.
    """
    cmd = parse_command(text)
    arg = _command_arg(text)
    chat_id = config.TELEGRAM_DRAFT_CHAT_ID

    if cmd == "/soy":
        _run_draft_action(
            "/draft/register",
            "POST",
            {"telegram_user_id": user_id, "name": arg},
            chat_id,
            "Soy",
        )
    elif cmd == "/pick":
        _run_draft_pick(user_id, arg, chat_id)
    elif cmd == "/estado":
        _run_draft_action("/draft/state", "GET", None, chat_id, "Estado")
    elif cmd == "/deshacer":
        _run_draft_action(
            "/draft/undo", "POST", {"telegram_user_id": user_id}, chat_id, "Deshacer"
        )
    elif cmd == "/exportar":
        _run_draft_action("/draft/export", "GET", None, chat_id, "Exportar")
    elif cmd == "/help":
        send_telegram_message(
            bot_token=config.TELEGRAM_BOT_TOKEN, chat_id=chat_id, text=_DRAFT_HELP_TEXT
        )
    elif cmd:
        logger.info(
            "Webhook: unknown draft command, ignoring", extra={"text": text[:50]}
        )


def _callback_from_user_id() -> str:
    """The tapping user's Telegram id, read off the raw update body.

    `extract_webhook_callback` doesn't carry `callback_query.from.id` —
    nothing else in the admin flow needs it. Draft-pick confirmation does,
    to check the tapper is the same user who ran `/pick`.
    """
    body = request.get_json(silent=True) or {}
    cq = body.get("callback_query") or {}
    return str(cq.get("from", {}).get("id") or "")


def _handle_draft_callback(cb: dict) -> None:
    """Dispatch a draft-group callback_query — only `d:<user_id>:<player_id>`
    (pick disambiguation) is allowed here. Any other prefix (`analizar:`,
    `e:`, `o:`) is refused, even though the group is never shown those
    buttons — defense in depth against a forged callback_data."""
    cb_data = cb.get("data", "")
    prefix, _, value = cb_data.partition(":")
    cb_id = cb["id"]

    if prefix != "d":
        answer_callback_query(config.TELEGRAM_BOT_TOKEN, cb_id)
        logger.info(
            "Webhook: refusing non-draft callback prefix from draft chat",
            extra={"prefix": prefix},
        )
        return

    parts = value.split(":", 1)
    if len(parts) != 2:
        answer_callback_query(config.TELEGRAM_BOT_TOKEN, cb_id)
        logger.info("Webhook: malformed draft callback", extra={"data": cb_data})
        return
    requesting_user_id, player_id_str = parts

    if _callback_from_user_id() != requesting_user_id:
        answer_callback_query(
            config.TELEGRAM_BOT_TOKEN,
            cb_id,
            text="❌ Solo quien pidió el fichaje puede confirmarlo.",
        )
        return

    try:
        player_id = int(player_id_str)
    except ValueError:
        answer_callback_query(config.TELEGRAM_BOT_TOKEN, cb_id)
        logger.info(
            "Webhook: non-int player_id in draft callback", extra={"data": cb_data}
        )
        return

    answer_callback_query(config.TELEGRAM_BOT_TOKEN, cb_id)
    chat_id = cb["chat_id"]
    edit_into = (chat_id, cb["message_id"]) if cb.get("message_id") else None
    if edit_into is not None:
        edit_message_reply_markup(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=chat_id,
            message_id=edit_into[1],
            reply_markup={"inline_keyboard": []},
        )

    def _call() -> None:
        try:
            data = _call_draft_api(
                "/draft/pick/confirm",
                "POST",
                {"telegram_user_id": requesting_user_id, "player_id": player_id},
            )
        except Exception as exc:
            logger.error(
                "Webhook: draft pick confirm failed",
                extra={"player_id": player_id, "error": str(exc)},
            )
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=chat_id,
                text=(
                    f"❌ Error al confirmar el fichaje: "
                    f"<code>{html.escape(str(exc))}</code>"
                ),
            )
            return
        message = data.get("message", "") or "Fichaje confirmado."
        if edit_into is not None:
            edit_message_text(
                bot_token=config.TELEGRAM_BOT_TOKEN,
                chat_id=chat_id,
                message_id=edit_into[1],
                text=message,
            )
        else:
            send_telegram_message(
                bot_token=config.TELEGRAM_BOT_TOKEN, chat_id=chat_id, text=message
            )

    _run_in_background(_call)


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
        if cb["chat_id"] == config.TELEGRAM_CHAT_ID:
            _handle_callback(cb)
        elif (
            config.TELEGRAM_DRAFT_CHAT_ID
            and cb["chat_id"] == config.TELEGRAM_DRAFT_CHAT_ID
        ):
            _handle_draft_callback(cb)
        else:
            logger.info(
                "Webhook: ignoring callback from unknown chat",
                extra={"chat_id": cb["chat_id"]},
            )
        return "", 200

    chat_id, text, user_id = extract_webhook_update(request)

    if chat_id == config.TELEGRAM_CHAT_ID:
        _handle_owner_message(text)
    elif config.TELEGRAM_DRAFT_CHAT_ID and chat_id == config.TELEGRAM_DRAFT_CHAT_ID:
        _handle_draft_message(text, user_id)
    else:
        logger.info(
            "Webhook: ignoring message from unknown chat",
            extra={"chat_id": chat_id},
        )

    return "", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
