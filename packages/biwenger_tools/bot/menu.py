"""Keyboard builders for the bot UI.

Two flavours of keyboard are used:

- **Persistent reply keyboard** (`main_menu_reply_keyboard`) — sits
  below the input field, always visible. The user taps a button and
  the label text is sent as a regular message; the webhook handler
  routes it via the label → action mapping. This is the primary UX.
- **Inline keyboards** (`managers_keyboard`) — only used for the
  manager picker, which is a one-shot two-step flow. `callback_data`
  is `analizar:<id|all>` so the handler can dispatch on the prefix.
"""

from typing import Iterable

# Main-menu actions. Order matters — the rows in the keyboard mirror this.
MAIN_MENU_ACTIONS = [
    ("analizar", "📊 Analizar"),
    ("mercado", "🛒 Mercado"),
    ("alinear", "📋 Alinear"),
    ("recomendar", "💡 Recomendar"),
    ("pujar", "💸 Pujar"),
    ("scrapper", "🧹 Scraper"),
]

# Reverse map for the webhook handler: `"📊 Analizar"` → `"analizar"`.
LABEL_TO_ACTION = {label: key for key, label in MAIN_MENU_ACTIONS}


def main_menu_reply_keyboard() -> dict:
    """Two-column persistent reply keyboard with every main-menu action.

    `is_persistent: true` keeps the keyboard visible across messages
    until the bot sends a `ReplyKeyboardRemove`. Tapping a button posts
    the label as a normal text message — the webhook routes it via
    `LABEL_TO_ACTION`.
    """
    rows = [
        [{"text": label} for _, label in MAIN_MENU_ACTIONS[i : i + 2]]
        for i in range(0, len(MAIN_MENU_ACTIONS), 2)
    ]
    return {
        "keyboard": rows,
        "is_persistent": True,
        "resize_keyboard": True,
    }


def managers_keyboard(managers: Iterable[dict]) -> dict:
    """Inline keyboard with one button per manager + a "TODOS" row.

    Each manager dict needs `id`, `name`, `is_me`. "Mi equipo" sits at
    the top (the api already orders the list that way), then the rivals,
    then the "TODOS" row.
    """
    rows = []
    for m in managers:
        if m.get("is_me"):
            label = f"🛡️ Mi equipo ({m['name']})"
        else:
            label = f"👤 {m['name']}"
        rows.append([{"text": label, "callback_data": f"analizar:{m['id']}"}])
    rows.append([{"text": "🌍 TODOS", "callback_data": "analizar:all"}])
    return {"inline_keyboard": rows}
