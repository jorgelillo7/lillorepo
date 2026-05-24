import hmac
from typing import Any, Optional

import requests

from core.utils import get_logger

logger = get_logger(__name__)

TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_SET_COMMANDS_URL = "https://api.telegram.org/bot{token}/setMyCommands"
TELEGRAM_SET_MENU_BUTTON_URL = "https://api.telegram.org/bot{token}/setChatMenuButton"
TELEGRAM_ANSWER_CALLBACK_URL = "https://api.telegram.org/bot{token}/answerCallbackQuery"
TELEGRAM_EDIT_MESSAGE_URL = "https://api.telegram.org/bot{token}/editMessageText"

# Hard limit on Bot API sendMessage; anything longer is truncated server-side.
TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    reply_markup: Optional[dict] = None,
) -> bool:
    """Sends a text message to a Telegram chat via the Bot API.

    Returns ``True`` if the message was delivered, ``False`` on any
    network or 4xx/5xx failure (also logged). Callers that need to
    react to a failed delivery (the auto-bid endpoint surfaces it as
    a 500 so the bot can notify the user) check the return value;
    fire-and-forget callers can keep ignoring it.

    Truncates messages over TELEGRAM_MAX_MESSAGE_LENGTH chars. For long
    content that needs splitting, do the splitting at the call site so
    each chunk forms a coherent unit. `reply_markup` accepts a Telegram
    InlineKeyboard dict (or any of the markup shapes the Bot API documents).
    """
    if len(text) > TELEGRAM_MAX_MESSAGE_LENGTH:
        logger.warning(
            "Telegram message exceeds limit — truncating.",
            extra={"length": len(text), "limit": TELEGRAM_MAX_MESSAGE_LENGTH},
        )
        text = text[: TELEGRAM_MAX_MESSAGE_LENGTH - 3] + "..."

    url = TELEGRAM_SEND_MESSAGE_URL.format(token=bot_token)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        logger.info("Telegram message sent.", extra={"chars": len(text)})
        return True
    except requests.RequestException as e:
        logger.error("Failed to send Telegram message.", extra={"error": str(e)})
        return False


def answer_callback_query(
    bot_token: str, callback_query_id: str, text: str = ""
) -> None:
    """Acknowledge an inline-keyboard tap.

    Telegram shows the loading spinner on the tapped button until this is
    called (or 30s pass). `text` (≤200 chars) flashes as a toast — keep it
    short or omit it; the real response should come via a regular message.
    """
    url = TELEGRAM_ANSWER_CALLBACK_URL.format(token=bot_token)
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text[:200]
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to answer callback_query.", extra={"error": str(e)})


def edit_message_text(
    bot_token: str,
    chat_id: str,
    message_id: int,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: Optional[dict] = None,
) -> None:
    """Replace an existing message's text (and optionally its keyboard).

    Used after a callback_query tap to swap the picker for a "processing…"
    status without leaving a stale menu hanging on the chat.
    """
    url = TELEGRAM_EDIT_MESSAGE_URL.format(token=bot_token)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to edit Telegram message.", extra={"error": str(e)})


def send_telegram_photo(
    bot_token: str,
    chat_id: str,
    image_bytes: bytes,
    caption: str = "",
) -> bool:
    """Sends a PNG image to a Telegram chat via sendPhoto.

    Returns ``True`` on success, ``False`` on any 4xx/5xx/network
    failure (also logged). Same contract as `send_telegram_message`.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    try:
        response = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"photo": ("image.png", image_bytes, "image/png")},
            timeout=30,
        )
        response.raise_for_status()
        logger.info("Telegram photo sent.", extra={"caption": caption[:40]})
        return True
    except requests.RequestException as e:
        logger.error("Failed to send Telegram photo.", extra={"error": str(e)})
        return False


class TelegramDeliveryError(RuntimeError):
    """Raised by the `_or_raise` helpers when Telegram refuses delivery.

    Surfaces upstream so route handlers can return 500 and the bot can
    post a fallback plaintext error to the user. Catch this specifically
    (not bare `Exception`) when you need to differentiate Telegram
    failures from upstream Biwenger/JP failures.
    """


def send_telegram_message_or_raise(
    bot_token: str,
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    reply_markup: Optional[dict] = None,
) -> None:
    """`send_telegram_message` that raises `TelegramDeliveryError` on
    failure. Use this when the caller is a request handler that should
    surface delivery failures as a non-2xx response."""
    if not send_telegram_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
        reply_markup=reply_markup,
    ):
        raise TelegramDeliveryError("Telegram message delivery failed")


def send_telegram_photo_or_raise(
    bot_token: str,
    chat_id: str,
    image_bytes: bytes,
    caption: str = "",
) -> None:
    """`send_telegram_photo` that raises `TelegramDeliveryError` on
    failure. Use in request handlers; the route returns 5xx and the
    bot tells the user."""
    if not send_telegram_photo(bot_token, chat_id, image_bytes, caption):
        raise TelegramDeliveryError("Telegram photo delivery failed")


def build_persistent_reply_keyboard(labels: list[str], cols: int = 2) -> dict:
    """Build a `ReplyKeyboardMarkup` dict laid out in `cols` columns.

    Pinned via `is_persistent: true` so it stays below the input across
    messages; `resize_keyboard: true` lets clients shrink button height
    when the device is narrow. Tapping a button posts its label as a
    plain text message — the webhook caller routes that text by exact
    match. Shared by every bot that needs a native-feeling button menu.
    """
    rows = [labels[i : i + cols] for i in range(0, len(labels), cols)]
    return {
        "keyboard": [[{"text": label} for label in row] for row in rows],
        "is_persistent": True,
        "resize_keyboard": True,
    }


def register_bot_commands(bot_token: str, commands: list[dict]) -> None:
    """Registers bot commands so they appear in the Telegram '/' menu.

    Each entry in `commands` must have 'command' (lowercase, no slash)
    and 'description' keys.
    """
    url = TELEGRAM_SET_COMMANDS_URL.format(token=bot_token)
    try:
        response = requests.post(url, json={"commands": commands}, timeout=15)
        response.raise_for_status()
        logger.info("Bot commands registered.", extra={"count": len(commands)})
    except requests.RequestException as e:
        logger.error("Failed to register bot commands.", extra={"error": str(e)})


def set_commands_menu_button(bot_token: str) -> None:
    """Sets the bot's menu button to show the registered command list.

    Renders as a blue "Menú" pill on the left of the input. Mostly
    superseded by `reset_menu_button_to_default` + a persistent reply
    keyboard for a cleaner look (see `configure_bot_commands`).
    """
    url = TELEGRAM_SET_MENU_BUTTON_URL.format(token=bot_token)
    try:
        response = requests.post(
            url, json={"menu_button": {"type": "commands"}}, timeout=15
        )
        response.raise_for_status()
        logger.info("Menu button set to 'commands'.")
    except requests.RequestException as e:
        logger.error("Failed to set menu button.", extra={"error": str(e)})


def reset_menu_button_to_default(bot_token: str) -> None:
    """Resets the bot's menu button to Telegram's `default`.

    Removes the blue "Menú" pill on the left of the input. The slash
    autocomplete that pops up when the user types `/` is unaffected
    — that comes from `register_bot_commands` (setMyCommands), not
    from the menu button. Idempotent.
    """
    url = TELEGRAM_SET_MENU_BUTTON_URL.format(token=bot_token)
    try:
        response = requests.post(
            url, json={"menu_button": {"type": "default"}}, timeout=15
        )
        response.raise_for_status()
        logger.info("Menu button reset to 'default'.")
    except requests.RequestException as e:
        logger.error("Failed to reset menu button.", extra={"error": str(e)})


def configure_bot_commands(bot_token: str, commands: list[dict]) -> None:
    """Idiomatic post-deploy setup shared by every bot in this repo.

    Registers `commands` for the slash autocomplete that Telegram pops
    up when the user types `/`, and resets the left "Menú" pill to the
    default — bots in this repo expose their main actions via a
    persistent reply keyboard (`build_persistent_reply_keyboard`), so
    a redundant pill on the left adds clutter without adding value.
    """
    register_bot_commands(bot_token, commands)
    reset_menu_button_to_default(bot_token)


def set_webhook(
    bot_token: str,
    url: str,
    secret_token: str,
    allowed_updates: Optional[list[str]] = None,
) -> None:
    """Register a webhook with Telegram.

    `allowed_updates` defaults to `["message", "callback_query"]` — that
    combination is the *only* one that lets the bot receive both text
    commands and inline-keyboard taps. Calling `setWebhook` without this
    parameter ends up at Telegram's default (which historically defaulted
    to `["message"]` for our bot — that's exactly the trap that broke
    every menu callback for hours until we found it).
    """
    if allowed_updates is None:
        allowed_updates = ["message", "callback_query"]
    api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    try:
        response = requests.post(
            api_url,
            json={
                "url": url,
                "secret_token": secret_token,
                "allowed_updates": allowed_updates,
            },
            timeout=15,
        )
        response.raise_for_status()
        logger.info(
            "Webhook set.",
            extra={"url": url, "allowed_updates": allowed_updates},
        )
    except requests.RequestException as e:
        logger.error("Failed to set webhook.", extra={"error": str(e)})


def parse_command(text: str) -> str:
    """Extract the bare command from a Telegram message text.

    '/analizar@bot arg' → '/analizar'
    '/HELP' → '/help'
    '' → ''
    """
    return text.lower().split()[0].split("@")[0] if text.strip() else ""


def extract_webhook_update(request: Any) -> tuple[str, str]:
    """Extract (chat_id, text) from a Flask webhook POST request body.

    Only handles plain text messages — callback_query updates go through
    `extract_webhook_callback`. Returns ('', '') for empty/malformed bodies
    or for updates that aren't text messages.
    """
    body = request.get_json(silent=True) or {}
    message = body.get("message", {})
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()
    return chat_id, text


def extract_webhook_callback(request: Any) -> Optional[dict]:
    """Pull the callback_query out of a Flask webhook POST.

    Returns a dict with `id`, `chat_id`, `message_id` and `data` when the
    update is an inline-keyboard tap, or None for any other update kind.
    `data` is the `callback_data` string the button was created with —
    typically `"prefix:value"`.
    """
    body = request.get_json(silent=True) or {}
    cq = body.get("callback_query")
    if not cq:
        return None
    message = cq.get("message") or {}
    return {
        "id": cq.get("id", ""),
        "chat_id": str(message.get("chat", {}).get("id", "")),
        "message_id": message.get("message_id"),
        "data": cq.get("data", ""),
    }


def validate_webhook_secret(request: Any, expected: str) -> bool:
    """Return True if the X-Telegram-Bot-Api-Secret-Token header matches.

    Uses constant-time comparison to avoid leaking the expected token via
    response-time side channels.
    """
    received = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    return hmac.compare_digest(received, expected)
