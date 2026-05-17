"""One-shot script: registers bot commands and sets the menu button.

Run once after deploy (or whenever commands change):
  python3 packages/biwenger_tools/telegram_bot/setup_commands.py

Requires TELEGRAM_BOT_TOKEN in the environment (or .env file).
"""

import sys

from packages.biwenger_tools.telegram_bot import config
from core.sdk.telegram import register_bot_commands, set_commands_menu_button

COMMANDS = [
    {"command": "analizar", "description": "Análisis completo de todos los equipos"},
    {"command": "myteam", "description": "Análisis solo de mi equipo"},
    {"command": "mercado", "description": "Solo el mercado"},
    {"command": "alinear", "description": "Aplica la mejor alineación posible"},
    {"command": "version", "description": "Versión desplegada del bot y del job"},
    {"command": "help", "description": "Muestra todos los comandos disponibles"},
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
