"""Draft — the board by tiers: who is interchangeable, and how fast each goes.

The question at every turn is not "who is best" but "in which group do the
fewest acceptable players survive until my next pick". This answers it with
three readings, all read-only:

- **Tiers per line**, league-sized: tier A holds the seven players with the
  most points per round in that line, B the next seven, and so on — one per
  manager, so a tier is what the league can take in one pass. Points per round
  is the measured total over the rounds the sample covers (the calibrated
  projection where nothing was measured, marked `~`).
- **The window**: how many of each line the league took between your turns in
  the last draft. Counts, not a probability on anyone — see SKILL.md on why.
- **Rival profiles**: each manager's spend and lines by round, last draft.

    bazel run //packages/biwenger_tools/.claude/skills/draft/scripts:tiers -- \\
        --season 27-28 --real-points <draft-real-points.csv> \\
        --exclude-file 26-27/exclusiones.txt --pick-position 3 \\
        --history 26-27/disponibilidad.csv --rivals-season 26-27
"""

import argparse
import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import archetypes as arch  # noqa: E402
import paths  # noqa: E402

TIER_LABELS = "ABCDEFGH"
CHEAP = 1_000_000


def build_tiers(rows, managers, rounds):
    """`{line: [[row, …] per tier]}`, best first; each row gains `per_round`."""
    out = {}
    for line in arch.POS:
        ranked = sorted(
            (
                {**r, "per_round": round(r["sf"] / rounds, 1)}
                for r in rows
                if r["pos"] == line
            ),
            key=lambda r: (-r["per_round"], r["price"]),
        )
        out[line] = [ranked[i : i + managers] for i in range(0, len(ranked), managers)]
    return out


def window_lines(history, start, end):
    """`{line: n}` picked strictly between global picks `start` and `end`."""
    return dict(Counter(h["line"] for h in history if start < h["pick"] < end))


def rival_profiles(picks, line_by_pick):
    """Per manager, last draft: first pick's price, average spend in rounds
    1-3 and 13-15, picks under 1M, and the lines of his first three picks."""
    by_manager = {}
    for p in sorted(picks, key=lambda p: p["global_pick"]):
        by_manager.setdefault(p["manager_name"], []).append(p)
    out = []
    for manager, mine in by_manager.items():

        def avg(rounds, mine=mine):
            prices = [p["price"] for p in mine if p["round"] in rounds]
            return sum(prices) / len(prices) if prices else None

        out.append(
            {
                "manager": manager,
                "slot": mine[0]["global_pick"],
                "first": mine[0]["price"],
                "early": avg(range(1, 4)),
                "late": avg(range(13, 16)),
                "cheap": sum(1 for p in mine if p["price"] < CHEAP),
                "first_lines": " ".join(
                    line_by_pick.get(p["global_pick"], "?") for p in mine[:3]
                ),
            }
        )
    return sorted(out, key=lambda p: p["slot"])


def _m(price):
    return "—" if price is None else f"{price / 1e6:.2f}M"


def render_tiers(tiers, shown):
    lines = []
    for line, groups in tiers.items():
        lines.append(f"## {arch.POS[line]}\n")
        lines.append(
            "| Nivel | Jugador | Equipo | Precio | Pts/jor | Tit | Fuente "
            "| Cal. 3 | Subida | © |"
        )
        lines.append("|:-:|---|---|--:|--:|:-:|:-:|:-:|--:|:-:|")
        for label, group in zip(TIER_LABELS, groups[:shown]):
            for r in group:
                rate = arch.start_rate(r)
                rise = r.get("rise")
                lines.append(
                    f"| {label} | {r['name']} | {r['team']} | {_m(r['price'])} "
                    f"| {r['per_round']} "
                    f"| {'—' if rate is None else f'{rate:.0%}'} "
                    f"| {arch.source_cell(r)} | {r.get('fixtures') or '—'} "
                    f"| {'—' if rise is None else f'{rise:+.0%}'} "
                    f"| {'©' if arch.tier(r) == 'durable' else ''} |"
                )
        lines.append("")
    return lines


def render_window(history, mine):
    lines = [
        "## Entre tus turnos, el draft anterior\n",
        "Cuántos de cada línea se llevó la liga entre un pick tuyo y el "
        "siguiente, la última vez. Es el ritmo de la línea, no a quién: con un "
        "solo draft de referencia, un número, no una predicción.\n",
        "| De tu pick | Al siguiente | Se van | POR | DEF | MED | DEL |",
        "|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for start, end in zip(mine, mine[1:]):
        gone = window_lines(history, start, end)
        cells = " | ".join(str(gone.get(c, 0)) for c in arch.POS)
        lines.append(f"| {start} | {end} | {end - start - 1} | {cells} |")
    lines.append("")
    return lines


def render_rivals(profiles):
    lines = [
        "## Cómo draftearon los rivales\n",
        "| Mánager | 1er pick | Su precio | Media R1-3 | Media R13-15 "
        "| < 1M | Líneas de sus 3 primeros |",
        "|---|--:|--:|--:|--:|--:|---|",
    ]
    for p in profiles:
        lines.append(
            f"| {p['manager']} | {p['slot']} | {_m(p['first'])} | {_m(p['early'])} "
            f"| {_m(p['late'])} | {p['cheap']} | {p['first_lines']} |"
        )
    lines.append("")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--season", default="26-27")
    ap.add_argument("--ranked", default="", help="por defecto <temporada>/ranked")
    ap.add_argument("--real-points", default="", help="CSV de fetch_real_points")
    ap.add_argument("--exclude-file", default="")
    ap.add_argument("--managers", type=int, default=7)
    ap.add_argument("--pick-position", type=int, default=0)
    ap.add_argument("--history", default="", help="disponibilidad.csv anterior")
    ap.add_argument(
        "--rivals-season", default="", help="temporada de Firestore a perfilar"
    )
    ap.add_argument("--tiers", type=int, default=4, help="niveles por línea")
    ap.add_argument("--out", default="", help="por defecto <temporada>/niveles.md")
    ap.add_argument(
        "--max-price", type=float, default=0, help="en millones, 0 = sin tope"
    )
    args = ap.parse_args()

    ranked = args.ranked or paths.season_path(args.season, paths.RANKED)
    excluded, reasons = (
        arch.read_exclusions(args.exclude_file) if args.exclude_file else ([], {})
    )
    rows, _, _ = arch.load(ranked, excluded)
    if args.real_points:
        arch.apply_real_points(rows, arch.read_real_points(args.real_points))
    if args.max_price:
        rows = [r for r in rows if r["price"] <= args.max_price * 1_000_000]
    rounds = max((r.get("rounds") or 0 for r in rows), default=0) or (
        arch.SEASON_ROUNDS
    )

    out = [
        f"# Niveles del draft — {args.season}\n",
        f"Puntos por jornada sobre las **{rounds} jornadas** que cubren los "
        "datos. Nivel = tantos jugadores como mánagers: lo que la liga se "
        "lleva de una pasada. **Fuente** `~` = sin medir, proyección "
        "calibrada: mídelo antes de fiarte de su nivel.\n",
    ]
    if reasons:
        out.append(f"Fuera por noticias: {len(reasons)} (ver --exclude-file).\n")
    out += render_tiers(build_tiers(rows, args.managers, rounds), args.tiers)
    mine = arch.my_picks(args.pick_position, args.managers, arch.SQUAD_SIZE)
    if args.history and mine:
        with open(args.history, encoding="utf-8") as fh:
            history = [
                {"pick": int(r["pick"]), "line": r["line"]} for r in csv.DictReader(fh)
            ]
        out += render_window(history, mine)
        if args.rivals_season:
            from board import load_picks

            line_by_pick = {h["pick"]: h["line"] for h in history}
            out += render_rivals(
                rival_profiles(load_picks(args.rivals_season), line_by_pick)
            )

    destination = args.out or paths.season_path(args.season, "niveles.md")
    with open(destination, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"Escrito: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
