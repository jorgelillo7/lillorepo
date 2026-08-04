"""Close the draft: block the write commands, record the history, say goodbye.

The mirror of `open.py`. The api closes itself when the last pick lands, but
only if that code is deployed when it lands — and `close_draft()` is reachable
no other way, so a draft that finished under an older revision stays open
forever. This is the manual door, and it is also the only step that writes the
season's history file: the api runs in Cloud Run and cannot touch the repo.

What closing buys: `/pick` and `/deshacer` stop reaching Biwenger. `/deshacer`
is a real `release_player` + `apply_bonus` — run in October it does not undo a
draft pick, it sells a player mid-season.

    python3 packages/biwenger_tools/scripts/draft/close.py [--write]

Read-only by default. Pass `--write` to close, report and send.
"""

import argparse
import os
import subprocess
import sys

from core.sdk.telegram import send_telegram_message
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import draft, draft_service

REPORT = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    ".claude",
    "skills",
    "draft",
    "scripts",
    "availability_report.py",
)

FAREWELL = """🏁 <b>Draft {season} — cerrado</b>

{picks} picks, {managers} plantillas completas. A partir de ahora
<code>/pick</code> y <code>/deshacer</code> quedan bloqueados: se opera desde la
app de Biwenger, que es dinero de la temporada en curso.

{table}

Nos vemos en la jornada 1. 🍀"""


def _table(state) -> str:
    """Per-manager spend, in draft order."""
    rows = []
    for manager_id in state.order:
        name = draft_service.LEAGUE_MEMBERS.get(manager_id, str(manager_id))
        spent = state.spent.get(manager_id, 0)
        budget = state.budgets.get(manager_id, 0)
        squad = len(state.squads.get(manager_id, ()))
        rows.append(
            f"· <b>{name}</b> — {squad} fichas, "
            f"{spent / 1e6:.2f}M de {budget / 1e6:.0f}M"
        )
    return "\n".join(rows)


def _write_history(season: str) -> bool:
    """Generate `history/{season}.md` + `.csv`. Shelled out, like the upload in
    `open.py`: the skill's scripts are read-only analysis and stay unimported."""
    result = subprocess.run(
        [sys.executable, REPORT, "--season", season],
        cwd=os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."),
        env={**os.environ, "PYTHONPATH": "."},
    )
    return result.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Close the draft")
    ap.add_argument("--write", action="store_true", help="do it (default: dry run)")
    ap.add_argument(
        "--reason",
        default="completed",
        help="recorded on the lifecycle document, for a close that is not the "
        "natural end of the draft",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="close with picks still pending — abandoning the draft, not ending it",
    )
    ap.add_argument("--skip-history", action="store_true", help="do not write history")
    args = ap.parse_args()

    season = config.DRAFT_SEASON
    state = draft_service._load_state()
    pending = draft.whose_turn(state)
    total = len(state.order) * draft.NUM_ROUNDS
    already = draft_service._lifecycle().get("closed")

    print(f"Season   : {season}")
    print(f"Picks    : {len(state.picks)} de {total}")
    print(f"Turno    : {'—' if pending is None else draft_service._mention(pending)}")
    print(f"Estado   : {'ya cerrado' if already else 'abierto'}")

    if already:
        # The api closed itself on the last pick. That path writes no files, so
        # the history step still has to run — this is the common case, not an
        # error.
        print("\nYa cerrado por la api. Queda el histórico:")
        return 0 if args.skip_history or _write_history(season) else 1
    if pending is not None and not args.force:
        print(
            f"\nQuedan {total - len(state.picks)} picks. Cerrar ahora abandona el "
            "draft: nadie podrá completar su plantilla con el bot. Repite con "
            "--force --reason '...' si es lo que quieres.",
            file=sys.stderr,
        )
        return 1

    text = FAREWELL.format(
        season=season,
        picks=len(state.picks),
        managers=len(state.order),
        table=_table(state),
    )
    print(f"\n--- mensaje ---\n{text}\n")
    if not args.write:
        print("Dry run — nada cerrado ni enviado. Repite con --write.")
        return 0

    draft_service.close_draft(args.reason)
    print(f"Draft cerrado ({args.reason}).")

    if not args.skip_history:
        if not _write_history(season):
            print(
                "El histórico no se ha escrito. Lánzalo a mano — el draft ya está "
                f"cerrado:\n  PYTHONPATH=. python3 {REPORT} --season {season}",
                file=sys.stderr,
            )

    token, chat = config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID
    if not (token and chat):
        print("Sin credenciales de Telegram — mensaje no enviado.", file=sys.stderr)
        return 1
    print("Mensaje enviado." if send_telegram_message(token, chat, text) else "FALLO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
