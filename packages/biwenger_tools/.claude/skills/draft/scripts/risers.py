"""Draft — who the market is buying, from two exports a few days apart.

A scouting signal the ranked CSV cannot carry. Draft prices are frozen, so what
you pay never moves; the real market keeps moving, and in pre-season it moves on
demand — no matches have been played, so a price that jumps is managers buying
a player they expect to start. That is exactly the fact a season total cannot
tell you, and it is independent of Jornada Perfecta.

Pair it with the frozen price and the bargains fall out: pay the old price for a
player the market has already re-rated.

    PYTHONPATH=. python3 .claude/skills/draft/scripts/risers.py \\
        --before ~/Downloads/primera-division.csv \\
        --after "~/Downloads/primera-division (1).csv" \\
        --ranked draft-ranked.csv --season 26-27 --me Jorge --max 2.55

Read-only. `--max` is in millions and caps what you pay, not the new price.

**A rise is a question, not an answer.** It says the crowd is buying, and the
crowd buys promoted-club players it has never seen play: in 26-27 the two
biggest risers among cheap defenders, +101% and +90%, both turned out to have
zero minutes in the top flight — their score came from the division below, and
JP does not distinguish. Confirm every riser with `fetch_real_points.py` before
spending on him. The column that decides is starts, not the rise.
"""

import argparse
import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

from board import _eur, _norm, board_state, load_market, load_picks  # noqa: E402

from archetypes import POS  # noqa: E402
import paths  # noqa: E402


def load_prices(path):
    """`{normalised name: price}` from a Biwenger market export."""
    prices = {}
    with open(os.path.expanduser(path), encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            try:
                prices[_norm(row["Jugador"])] = int(row["Precio"])
            except (KeyError, ValueError):
                continue
    return prices


def main():
    ap = argparse.ArgumentParser(description="Quién está subiendo en el mercado real")
    ap.add_argument("--before", required=True, help="market export, the earlier one")
    ap.add_argument("--after", required=True, help="market export, the later one")
    ap.add_argument(
        "--ranked", default="", help="por defecto <temporada>/draft-ranked.csv"
    )
    ap.add_argument("--season", default="26-27")
    ap.add_argument("--me", default="Jorge")
    ap.add_argument("--max", type=float, default=0, help="en millones, 0 = sin tope")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--max-per-team", type=int, default=2)
    args = ap.parse_args()

    before, after = load_prices(args.before), load_prices(args.after)
    ranked = args.ranked or paths.season_path(args.season, paths.RANKED)
    market = load_market(ranked)
    picks = load_picks(args.season)
    free, _ = board_state(market, picks)
    mine = [p for p in picks if _norm(p.get("manager_name")) == _norm(args.me)]
    clubs = Counter(
        market[_norm(p["player_name"])]["team"]
        for p in mine
        if _norm(p["player_name"]) in market
    )
    cap = int(args.max * 1_000_000) if args.max else None

    rows = []
    for row in free:
        key = _norm(row["name"])
        old = before.get(key)
        new = after.get(key)
        if not old or not new or (cap and row["price"] > cap):
            continue
        rows.append({**row, "old": old, "new": new, "rise": (new - old) / old})

    print(f"# Subidas del mercado real · {len(rows)} libres comparados\n")
    print(
        f"Pagas el precio congelado de `{os.path.basename(ranked)}`. La "
        "subida es del mercado de verdad entre las dos exportaciones — en "
        "pretemporada eso es demanda de mánagers, no rendimiento.\n"
    )
    for code in POS:
        selection = sorted(
            (r for r in rows if r["pos"] == code), key=lambda r: -r["rise"]
        )[: args.top]
        if not selection:
            continue
        print(f"\n## {POS[code]}\n")
        print("| Jugador | Equipo | Pagas | Antes | Ahora | Subida | SF |")
        print("|---|---|--:|--:|--:|--:|--:|")
        for r in selection:
            note = " 🎲" if r["placeholder"] else ""
            if clubs[r["team"]] >= args.max_per_team:
                note += " ⛔"
            print(
                f"| {r['name']}{note} | {r['team']} | **{_eur(r['price'])}** "
                f"| {_eur(r['old'])} | {_eur(r['new'])} "
                f"| **{r['rise'] * 100:+.0f}%** | {r['sf']} |"
            )
    print("\n🎲 sin datos de JP · ⛔ ya tienes el tope de ese club.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
