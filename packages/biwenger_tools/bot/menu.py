"""Keyboard builders for the bot UI.

Two flavours of keyboard are used:

- **Persistent reply keyboard** (`main_menu_reply_keyboard`) — sits
  below the input field, always visible. The user taps a button and
  the label text is sent as a regular message; the webhook handler
  routes it via the label → action mapping. This is the primary UX.
- **Inline keyboards** (`managers_keyboard`, `pact_keyboard`) — the
  manager picker (`analizar:<id|all>`) and the non-aggression pact
  editor (`pact:<id>`), both dispatched on the callback prefix.
"""

from typing import Iterable

from core.sdk.telegram import build_persistent_reply_keyboard

# Main-menu actions. Order matters — the rows in the keyboard mirror this.
# Layout (2 columns):
#   Lectura/análisis  ·  Decisiones tácticas
#   Acciones mercado  ·  Operación crítica / utilidad
MAIN_MENU_ACTIONS = [
    ("analizar", "📊 Analizar"),
    ("mercado", "🛒 Mercado"),
    ("alinear", "📋 Alinear"),
    ("recomendar", "💡 Recomendar"),
    ("comparar", "⚖️ Comparar"),
    ("ofertas", "📥 Ofertas"),
    ("pujar", "💸 Pujar"),
    ("emergencia", "🚨 Emergencia"),
    ("scrapper", "🧹 Scraper"),
]

# Reverse map for the webhook handler: `"📊 Analizar"` → `"analizar"`.
LABEL_TO_ACTION = {label: key for key, label in MAIN_MENU_ACTIONS}


def main_menu_reply_keyboard() -> dict:
    """Two-column persistent reply keyboard with every main-menu action."""
    return build_persistent_reply_keyboard([label for _, label in MAIN_MENU_ACTIONS])


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


PACT_ON = "🤝"
PACT_OFF = "⚔️"


def pact_keyboard(managers: Iterable[dict]) -> dict:
    """Inline keyboard for `/pacto`: one toggle per rival manager.

    Each manager dict needs `id`, `name`, `pacted`; `is_me` is skipped —
    there is no pact with yourself, and a button that can only ever be a
    mistake should not be on the screen. 🤝 means protected, ⚔️ fair game;
    tapping flips it.
    """
    rows = [
        [
            {
                "text": f"{PACT_ON if m.get('pacted') else PACT_OFF} {m['name']}",
                "callback_data": f"pact:{m['id']}",
            }
        ]
        for m in managers
        if not m.get("is_me")
    ]
    return {"inline_keyboard": rows}
