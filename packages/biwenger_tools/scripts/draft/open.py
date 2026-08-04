"""Open the draft: publish the frozen market CSV, start the clock, greet the group.

Uploading the closed-market CSV is the one act that unambiguously means "the
draft starts now", so it is what opens it. Doing the four steps by hand left the
26-27 draft with no starting instant at all: wait times only began at pick 49,
and the earlier ones had to be dug out of Cloud Logging afterwards.

    python3 packages/biwenger_tools/scripts/draft/open.py \\
        --csv ~/Downloads/primera-division.csv [--write]

Read-only by default. Pass `--write` to upload, open and send.
"""

import argparse
import os
import subprocess
import sys

from core.constants import LEAGUE_MEMBERS
from core.sdk.telegram import send_telegram_message
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import draft, draft_service

WELCOME = """🏁 <b>Draft {season} — abierto</b>

Mercado congelado: {players} jugadores, precios cerrados. El que veis hoy es el
que se paga, pase lo que pase con el mercado real durante el draft.

<b>Cómo va</b>
· <code>/soy &lt;nombre&gt;</code> para registrarte — hazlo antes de tu turno.
· <code>/pick &lt;jugador&gt;</code> cuando te toque. El bot avisa al siguiente.
· <code>/equipos</code> y <code>/resumen</code> para mirar sin tocar nada.

<b>Dos avisos</b>
· Los fichajes se aplican <b>de verdad</b> en Biwenger, con la cuenta de Jorge.
  Si el bot va lento, esperad — no repitáis el comando.
· No abuséis de la app durante el draft: Biwenger corta por exceso de
  peticiones y el corte es <b>para toda la liga</b>, no solo para quien lo causa.

Orden: {order}

¡Suerte! 🎲"""


def _upload(csv_path: str, url: str) -> str:
    """Copy the CSV to the public bucket object the API reads."""
    if not url.startswith("https://storage.googleapis.com/"):
        raise SystemExit(f"DRAFT_MARKET_CSV_URL is not a bucket URL: {url}")
    target = "gs://" + url[len("https://storage.googleapis.com/") :]
    subprocess.run(["gsutil", "cp", csv_path, target], check=True)
    subprocess.run(["gsutil", "acl", "ch", "-u", "AllUsers:R", target], check=True)
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description="Open the draft")
    ap.add_argument("--csv", required=True, help="frozen closed-market export")
    ap.add_argument("--write", action="store_true", help="do it (default: dry run)")
    ap.add_argument("--skip-upload", action="store_true", help="CSV already in place")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        raise SystemExit(f"{args.csv}: not found")
    with open(args.csv, encoding="utf-8-sig") as fh:
        players = max(0, sum(1 for _ in fh) - 1)

    state = draft_service.load_state()
    order = " · ".join(LEAGUE_MEMBERS.get(m, str(m)) for m in state.order)
    text = WELCOME.format(season=config.DRAFT_SEASON, players=players, order=order)
    rounds = len(state.order) * draft.NUM_ROUNDS

    print(f"Season   : {config.DRAFT_SEASON}")
    print(f"CSV      : {args.csv} ({players} jugadores)")
    print(f"Bucket   : {config.DRAFT_MARKET_CSV_URL}")
    print(f"Order    : {order}")
    print(f"Picks    : {rounds}")
    print(f"Ya hechos: {len(state.picks)}")
    print(f"\n--- mensaje ---\n{text}\n")

    if state.picks:
        print(
            "AVISO: ya hay picks aplicados. Abrir de nuevo reinicia el reloj "
            "del turno, no borra nada.",
            file=sys.stderr,
        )
    if not args.write:
        print("Dry run — nada subido ni enviado. Repite con --write.")
        return 0

    if not args.skip_upload:
        print(f"Subido a {_upload(args.csv, config.DRAFT_MARKET_CSV_URL)}")
    draft_service.reset_market_cache()
    result = draft_service.open_draft(csv_url=config.DRAFT_MARKET_CSV_URL)
    print(f"Draft abierto: {result}")

    token, chat = config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID
    if not (token and chat):
        print("Sin credenciales de Telegram — mensaje no enviado.", file=sys.stderr)
        return 1
    print("Mensaje enviado." if send_telegram_message(token, chat, text) else "FALLO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
