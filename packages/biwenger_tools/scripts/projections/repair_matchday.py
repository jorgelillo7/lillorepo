"""Re-collect one stored round's outcome from its whole matchday, and mark the
matchday's other rounds as covered by it.

    PYTHONPATH=. <venv>/bin/python \\
        packages/biwenger_tools/scripts/projections/repair_matchday.py \\
        --round 5125            # dry run: old and new points side by side
    ... --round 5125 --apply    # write them

`<venv>` is one built from `requirements_lock.txt` on Python 3.14, never the
system `python3` (see `CLAUDE.md`).

For outcomes stored before the ledger read a matchday across its postponed
round ids: J6 (5125) holds Iván Romero as a zero because his game was filed
under 5176. The daily collection now reads the whole matchday; this rewrites
an outcome it collected before that.

Reads one player-detail per fielded or stored player, sequentially, a second
apart, from the window shared with the phone app. Refuses to write if any
fielded player still has no report. ADC for Firestore, Biwenger credentials
from `.env`.
"""

import argparse
import sys
from datetime import datetime
from types import SimpleNamespace

from core.constants import MADRID_TZ
from core.sdk.biwenger import BiwengerClient
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import (
    projection_ledger,
    projection_ledger_capture,
    projection_ledger_store,
)
from packages.biwenger_tools.api.logic.orchestration import build_biwenger_session


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    biwenger = build_biwenger_session()
    players, _ = BiwengerClient.get_competition_maps(config.ALL_PLAYERS_DATA_URL)
    season_rounds = (biwenger.get_round().get("season") or {}).get("rounds") or []
    documents = projection_ledger_store.list_all()
    document = next((d for d in documents if d.get("round_id") == args.round), None)
    if document is None:
        print(f"No hay documento para la ronda {args.round}.")
        return 1

    matchday = projection_ledger.matchday_ids(args.round, season_rounds)
    print(f"Ronda {args.round} ({document.get('round_name')}): jornada {matchday}")

    old = document.get("actual") or {}
    stored_ids = [int(i) for i in (old.get("player_points") or {})]
    squad_ids = [p["bw_id"] for p in document.get("players") or []] or stored_ids
    ctx = SimpleNamespace(biwenger=biwenger, biwenger_players=players)
    outcome, missing = projection_ledger_capture._outcome_for(
        ctx, args.round, squad_ids, matchday=matchday
    )
    if outcome is None:
        print(f"Sin informe para {missing}: no se escribe nada.")
        return 1

    old_points = old.get("player_points") or {}
    for bw_id, points in sorted(outcome["player_points"].items()):
        before = old_points.get(bw_id)
        mark = "" if before == points else f"   (antes {before})"
        name = (players.get(bw_id) or {}).get("name") or bw_id
        print(f"  {name:24s} {points:4d}{mark}")
    print(f"Total del once: {old.get('applied_total')} → {outcome['applied_total']}")

    siblings = [
        d
        for d in documents
        if d.get("round_id") in matchday and d.get("round_id") != args.round
    ]
    for sibling in siblings:
        print(f"Ronda {sibling['round_id']}: quedará cubierta por {args.round}.")

    if not args.apply:
        print("\nEnsayo: no se ha escrito nada. Repite con --apply.")
        return 0

    season = document.get("season") or config.CURRENT_SEASON
    projection_ledger_store.write_actual(season, args.round, outcome)
    now = datetime.now(MADRID_TZ)
    for sibling in siblings:
        projection_ledger_store.write_actual(
            sibling.get("season") or season,
            sibling["round_id"],
            projection_ledger.covered_outcome(args.round, now),
        )
    print("Escrito.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
