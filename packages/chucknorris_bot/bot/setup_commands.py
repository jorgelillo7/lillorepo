"""One-shot script: registers bot commands and sets the menu button.

Run once after deploy (or whenever commands change):
  python3 packages/chucknorris_bot/bot/setup_commands.py

Requires TELEGRAM_BOT_TOKEN in the environment (or .env file).
"""

import sys

from core.sdk.telegram import register_bot_commands, set_commands_menu_button
from packages.chucknorris_bot.bot import config

COMMANDS = [
    {"command": "random", "description": "Random Chuck Norris fact"},
    {"command": "science", "description": "Science fact"},
    {"command": "food", "description": "Food fact"},
    {"command": "animal", "description": "Animal fact"},
    {"command": "dev", "description": "Developer fact"},
    {"command": "help", "description": "Show all commands"},
]


def main():
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set.", file=sys.stderr)
        sys.exit(1)

    print("Registering commands…")
    register_bot_commands(token, COMMANDS)

    print("Setting menu button…")
    set_commands_menu_button(token)

    print("Done.")


if __name__ == "__main__":
    main()
