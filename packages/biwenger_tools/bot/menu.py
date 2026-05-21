"""Inline-keyboard builders for the bot's /menu UI.

The webhook handler in ``app.py`` calls these to produce the dicts that
Telegram's ``reply_markup`` expects. Keep them pure and stateless — the
network round-trips happen there, not here.

`callback_data` strings are namespaced with a `"prefix:value"` form so
the handler can dispatch on the prefix:

- ``menu:<action>``     → main menu tap (analizar / mercado / …).
- ``analizar:<id|all>`` → manager picker tap.
"""

from typing import Iterable

# Main-menu actions. Order matters — the rows in the keyboard mirror this.
MAIN_MENU_ACTIONS = [
    ("analizar", "📊 Analizar"),
    ("mercado", "🛒 Mercado"),
    ("alinear", "📋 Alinear"),
    ("recomendar", "💡 Recomendar"),
    ("scrapper", "🧹 Scraper"),
]


def main_menu_keyboard() -> dict:
    """Two-column inline keyboard with every main-menu action."""
    buttons = [
        {"text": label, "callback_data": f"menu:{key}"}
        for key, label in MAIN_MENU_ACTIONS
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return {"inline_keyboard": rows}


def managers_keyboard(managers: Iterable[dict]) -> dict:
    """Vertical keyboard with one button per manager + a "TODOS" row.

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
