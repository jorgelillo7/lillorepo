"""One-shot post-deploy hook: registers bot commands, sets the menu
button, and (re-)registers the webhook with the right `allowed_updates`.

CI runs this after every bot deploy (see `deploy-bot` in
`.github/workflows/deploy.yml`). Locally you can run it the same way:

  python3 packages/biwenger_tools/bot/setup_commands.py

Required env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`. Optional
`BIWENGER_BOT_URL` (full webhook URL, e.g.
`https://biwenger-bot-.../telegram/webhook`); when set the script also
calls `setWebhook` with `allowed_updates=["message", "callback_query"]`.
Skipping the webhook registration locally is fine — Telegram remembers
the last URL configured.
"""

import os
import sys

from packages.biwenger_tools.bot import config
from core.sdk.telegram import configure_bot_commands, set_webhook

COMMANDS = [
    {"command": "menu", "description": "Menú visual con botones (recomendado)"},
    {"command": "analizar", "description": "Análisis (te pregunta a quién)"},
    {"command": "mercado", "description": "Solo el mercado"},
    {"command": "alinear", "description": "Aplica la mejor alineación posible"},
    {
        "command": "preview",
        "description": "Previsualiza la alineación sin aplicarla",
    },
    {
        "command": "recomendar",
        "description": "Qué fichar si me clausulan (top 3 por posición)",
    },
    {
        "command": "pujar",
        "description": "Lanza el auto-bid del mercado diario por tiers",
    },
    {
        "command": "ofertas",
        "description": "Ofertas entrantes con recomendación + botones",
    },
    {
        "command": "emergencia",
        "description": "Clausulazo de emergencia con confirmación (irreversible)",
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

    print("Configuring commands + resetting menu button to default…")
    configure_bot_commands(token, COMMANDS)

    bot_url = os.getenv("BIWENGER_BOT_URL", "").strip()
    if bot_url:
        secret = config.TELEGRAM_WEBHOOK_SECRET
        if not secret:
            print(
                "ERROR: TELEGRAM_WEBHOOK_SECRET required to set webhook.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Setting webhook → {bot_url}")
        set_webhook(token, bot_url, secret)
    else:
        print("Skipping webhook (BIWENGER_BOT_URL not set).")

    print("Done.")


if __name__ == "__main__":
    main()
