"""Persistent reply keyboard for the Chuck Norris bot.

Same pattern as `biwenger_tools/bot/menu.py`: a list of
`(category, label)` pairs drives both the keyboard layout and the
label → action router consumed by the webhook handler.
"""

from core.sdk.telegram import build_persistent_reply_keyboard

# Main-menu actions. Order matters — the keyboard rows mirror this.
# Categories without an emoji button (version, help) stay accessible
# via slash commands.
MAIN_MENU_ACTIONS = [
    ("random", "🎲 Random"),
    ("science", "🧪 Science"),
    ("food", "🍔 Food"),
    ("animal", "🐾 Animal"),
    ("dev", "💻 Dev"),
]

# Reverse map for the webhook handler: `"🎲 Random"` → `"random"`.
LABEL_TO_CATEGORY = {label: key for key, label in MAIN_MENU_ACTIONS}


def main_menu_reply_keyboard() -> dict:
    """Two-column persistent reply keyboard with every fact category."""
    return build_persistent_reply_keyboard([label for _, label in MAIN_MENU_ACTIONS])
