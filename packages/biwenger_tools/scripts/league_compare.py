"""Rank every squad in the league by value and by projection, to your own chat.

    PYTHONPATH=. python3 packages/biwenger_tools/scripts/league_compare.py [--write]

Read-only by default. `--write` sends.

Deliberately **not** the draft group: this is the message you read to decide
whether to buy, and broadcasting the projection of every rival's squad to the
rivals themselves gives away the only edge the tooling provides.

Not under `scripts/draft/` for the same reason it is useful at all — it asks
about the squads people own today, which after the first clausulazo has nothing
to do with what anybody drafted. The post-draft report answers the same two
questions about the draft, and shares this module's renderer.

Costs one squad read per manager plus the competition payload and one Jornada
Perfecta fetch — about nine requests, the same as the bot's `/analizar TODOS`.
"""

import argparse
import sys
from datetime import datetime

from core.constants import MADRID_TZ
from core.sdk.telegram import send_telegram_message
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import league_compare
from packages.biwenger_tools.api.logic.orchestration import build_context


def main() -> int:
    ap = argparse.ArgumentParser(description="League squads ranked, to your chat")
    ap.add_argument("--write", action="store_true", help="enviar (por defecto: ensayo)")
    args = ap.parse_args()

    summary = league_compare.collect(build_context())
    if not summary:
        print("La liga no devolvió ninguna plantilla.", file=sys.stderr)
        return 1

    today = datetime.now(MADRID_TZ).strftime("%d/%m")
    message = league_compare.render(
        summary,
        title=f"📊 <b>La liga hoy</b> · {today}",
        note=(
            "Valor de mercado actual y proyección de Jornada Perfecta para la "
            "próxima jornada. Son dos preguntas distintas y por eso van sin "
            "combinar: un equipo caro no es un equipo que puntúe."
        ),
    )
    print(message)

    if not args.write:
        print("\nEnsayo — nada enviado. Repite con --write.")
        return 0

    token, chat = config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID
    if not (token and chat):
        print("Sin credenciales de Telegram.", file=sys.stderr)
        return 1
    ok = send_telegram_message(token, chat, message)
    print("Enviado." if ok else "FALLO al enviar.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
