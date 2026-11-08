"""Where each manager's league points come from: the SofaScore base, or the
league's bonuses for playing, winning and keeping a clean sheet — and how much
of each round its two best players carried.

    PYTHONPATH=. <venv>/bin/python \\
        packages/biwenger_tools/scripts/projections/squad_gap.py

`<venv>` is one built from `requirements_lock.txt` on Python 3.14, never the
system `python3` (see `CLAUDE.md`).

Read-only: it writes nothing, so there is no `--apply`.

**How to read the output: `docs/technical/backend/projection-ledger.md`,
"Where the gap comes from".** It is the evidence the
`openspec/changes/squad-composition/` gate asks for.

One authenticated `rounds/league` read per finished matchday, and one
player-detail read per player any manager fielded or benched, through
`report.py`'s cache. The player endpoint shares a small window with the phone
app — it answered 429 after about 200 reads — so `--max-requests` is a hard
cap and a 429 stops the run. A cached player is never re-read: delete
`.cache/players` to pick up rounds played since. A manager's round with a
player still unread is left out and counted, never scored as a zero.

Biwenger credentials from `.env`.
"""

import argparse
import os
import time

from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import projection_ledger
from packages.biwenger_tools.api.logic import squad_gap as sg
from packages.biwenger_tools.api.logic.orchestration import build_biwenger_session
from packages.biwenger_tools.api.logic.real_points import personalizado
from packages.biwenger_tools.scripts.projections.report import _PlayerFetcher


def _matchdays(biwenger) -> list[tuple[str, list[int]]]:
    season = (biwenger.get_round().get("season") or {}).get("rounds") or []
    finished = {r["id"] for r in season if r.get("status") == "finished"}
    ready = projection_ledger.finished_matchdays(season, finished)
    seen, out = set(), []
    for r in season:
        if r["id"] not in ready or r["id"] in seen:
            continue
        ids = projection_ledger.matchday_ids(r["id"], season)
        seen.update(ids)
        out.append((r.get("name") or str(r["id"]), ids))
    return out


def _stats_for(player: dict, matchday: list[int]) -> dict:
    reports = [
        rep
        for rep in player.get("reports") or []
        if ((rep.get("match") or {}).get("round") or {}).get("id") in matchday
    ]
    return personalizado(reports, player.get("position"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--delay", type=float, default=1.2)
    ap.add_argument("--max-requests", type=int, default=60)
    ap.add_argument(
        "--cache-dir",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".cache", "players"
        ),
    )
    args = ap.parse_args()

    biwenger = build_biwenger_session()
    players = biwenger.get_all_players_data_map(config.ALL_PLAYERS_DATA_URL)
    fetcher = _PlayerFetcher(args.cache_dir, args.delay, args.max_requests)

    rows: dict[str, list] = {}
    errors, skipped = [], 0
    for name, matchday in _matchdays(biwenger):
        standings = (biwenger.get_round_league(matchday[0]).get("league") or {}).get(
            "standings"
        ) or []
        time.sleep(args.delay)
        for entry in standings:
            lineup = entry.get("lineup") or {}
            if lineup.get("points") is None:
                continue
            ids = [
                i
                for i in (lineup.get("players") or []) + (lineup.get("reserves") or [])
                if i
            ]
            details = {}
            for bw_id in ids:
                slug = (players.get(bw_id) or {}).get("slug")
                detail = fetcher.player(slug) if slug else None
                if detail is not None:
                    details[bw_id] = detail
            if len(details) < len(ids):
                skipped += 1
                continue
            stats = {i: _stats_for(d, matchday) for i, d in details.items()}
            positions = {i: d.get("position") for i, d in details.items()}
            row = sg.manager_round(lineup, stats, positions)
            rows.setdefault(entry.get("name") or "?", []).append(row)
            errors.append(row["points"] - lineup["points"])
        print(f"{name}: leída", flush=True)

    if fetcher.rate_limited:
        print("\nBiwenger respondió 429: parada. Repite cuando se abra la ventana.")
    print(
        f"\nRondas de mánager sin todos sus jugadores leídos (fuera): {skipped}"
        f"\nReconstrucción contra la liga: {sum(e == 0 for e in errors)}"
        f"/{len(errors)} exactas, error medio "
        f"{sum(abs(e) for e in errors) / max(len(errors), 1):.1f} puntos\n"
    )
    print(
        f"{'Mánager':22s} {'n':>2s} {'pts':>5s} {'base':>5s} {'juega':>5s} "
        f"{'V−D':>4s} {'PaC':>4s} {'resto':>5s} {'V':>3s} {'D':>3s} {'top2':>5s}"
    )
    print("(por jornada, salvo V y D, que son totales)")
    for s in sg.summarize(rows):
        n = s["rounds"]
        print(
            f"{s['manager'][:22]:22s} {n:2d} {s['points'] / n:5.1f} "
            f"{s['base'] / n:5.1f} {s['play'] / n:5.1f} {s['result'] / n:4.1f} "
            f"{s['clean'] / n:4.1f} {s['other'] / n:5.1f} {s['wins']:3d} "
            f"{s['losses']:3d} {s['top_two_share']:5.0%}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
