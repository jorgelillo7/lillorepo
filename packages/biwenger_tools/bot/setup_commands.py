"""One-shot script: registers bot commands and sets the menu button.

Run once after deploy (or whenever commands change):
  python3 packages/biwenger_tools/bot/setup_commands.py

Requires TELEGRAM_BOT_TOKEN in the environment (or .env file).
"""

import sys

from packages.biwenger_tools.bot import config
from core.sdk.telegram import register_bot_commands, set_commands_menu_button

COMMANDS = [
    {"command": "menu", "description": "Menú visual con botones (recomendado)"},
    {"command": "analizar", "description": "Análisis (te pregunta a quién)"},
    {"command": "mercado", "description": "Solo el mercado"},
    {"command": "alinear", "description": "Aplica la mejor alineación posible"},
    {
        "command": "recomendar",
        "description": "Qué fichar si me clausulan (top 3 por posición)",
    },
    {
        "command": "scrapper",
        "description": "Lanza el scraper a demanda (te avisa al acabar)",
    },
    {"command": "version", "description": "Versión desplegada del bot y de la API"},
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
