"""One-shot post-deploy hook: registers bot commands, sets the menu
button, and (re-)registers the webhook with the right `allowed_updates`.

CI runs this after every bot deploy (see `deploy-bot` in
`.github/workflows/deploy.yml`). Locally you can run it the same way:

  python3 packages/biwenger_tools/bot/setup_commands.py

Required env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`,
`TELEGRAM_CHAT_ID` (the owner's list is scoped to it), and
`TELEGRAM_DRAFT_CHAT_ID` for the draft group's list. Optional
`BIWENGER_BOT_URL` (full webhook URL, e.g.
`https://biwenger-bot-.../telegram/webhook`); when set the script also
calls `setWebhook` with `allowed_updates=["message", "callback_query"]`.
Skipping the webhook registration locally is fine — Telegram remembers
the last URL configured.
"""

import os
import sys

from core.sdk.telegram import configure_bot_commands, set_webhook
from packages.biwenger_tools.bot import config

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
        "command": "comparar",
        "description": "Valor y proyección de todas las plantillas",
    },
    {
        "command": "saldos",
        "description": "Saldo y puja máxima de cada manager",
    },
    {"command": "top", "description": "Los 5 mejores de cada manager"},
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
        "command": "pacto",
        "description": "Pacto de no agresión: a quién no clausular",
    },
    {
        "command": "scrapper",
        "description": "Lanza el scraper a demanda (te avisa al acabar)",
    },
    {"command": "publico", "description": "Quién puede ver la info pública"},
    {"command": "version", "description": "Versión desplegada del bot y de la API"},
    {"command": "help", "description": "Muestra todos los comandos disponibles"},
]

# Registered scoped to the draft supergroup, so the `/` menu there offers these
# and none of the admin commands above. The scoped list wins over the global one
# inside that chat.
DRAFT_COMMANDS = [
    {"command": "pick", "description": "Ficha a un jugador en tu turno"},
    {"command": "estado", "description": "Turno actual, presupuestos y plantillas"},
    {"command": "soy", "description": "Vincula tu cuenta de Telegram con tu equipo"},
    {"command": "deshacer", "description": "Revierte el último fichaje (admin)"},
    {"command": "exportar", "description": "Exporta todos los fichajes del draft"},
]


# The `/` menu of every private chat that has no list of its own: what an
# allowlisted member may run. Strangers see it too and get no reply.
PUBLIC_COMMANDS = [
    {
        "command": "saldos",
        "description": "Saldo, cláusulas y puja máxima de cada manager",
    },
    {"command": "movimientos", "description": "Movimientos de las últimas 24 h"},
    {"command": "analizar", "description": "Plantilla de un rival (te pregunta cuál)"},
    {"command": "top", "description": "Los 5 mejores de cada manager"},
    {"command": "mercado", "description": "Clausulazos en la web"},
    {"command": "ayuda", "description": "Qué puedo consultar"},
]


def main():
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set.", file=sys.stderr)
        sys.exit(1)
    owner_chat_id = config.TELEGRAM_CHAT_ID
    if not owner_chat_id:
        # Without it the owner's list cannot be scoped, and publishing it
        # globally is exactly what the three blocks exist to prevent.
        print("ERROR: TELEGRAM_CHAT_ID not set.", file=sys.stderr)
        sys.exit(1)

    # Telegram shows the narrowest list that matches a chat: chat >
    # all_private_chats > default. Each block reaches only its own chats.
    print("Default scope: no commands (other groups see none)…")
    configure_bot_commands(token, [])
    print("Private chats: the public commands…")
    configure_bot_commands(token, PUBLIC_COMMANDS, scope={"type": "all_private_chats"})
    print(f"Owner chat {owner_chat_id}: base and management commands…")
    configure_bot_commands(
        token, COMMANDS, scope={"type": "chat", "chat_id": owner_chat_id}
    )

    draft_chat_id = config.TELEGRAM_DRAFT_CHAT_ID
    if draft_chat_id:
        print(f"Draft group {draft_chat_id}: draft commands…")
        configure_bot_commands(
            token,
            DRAFT_COMMANDS,
            scope={"type": "chat", "chat_id": draft_chat_id},
        )
    else:
        print("Skipping draft commands (draft_chat_id not set).")

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
