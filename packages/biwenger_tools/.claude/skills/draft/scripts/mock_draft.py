"""Draft — a mock draft to rehearse the plan against the league's habits.

Rivals pick the best projected player near what each of them spent in that
round of the last draft; you pick by the rules the skill teaches — value
(measured over projected, price charged, nothing over `MAX_PICK_PRICE`), the
line whose good players run out before your next turn first, a bench that
plays, and the reserve keeper last at the floor. Read-only and offline.

What it is for: seeing the plan play out, and above all **who in your fifteen
is still unmeasured** — it writes them to `--shortlist-out` for the next
`fetch_real_points` run. Measure, re-run, until the fifteen stops changing.
Rivals are a crude model of last year; the table at the end is a projection,
not a forecast of the league.

    bazel run //packages/biwenger_tools/.claude/skills/draft/scripts:mock_draft -- \\
        --season 27-28 --real-points <draft-real-points.csv> \\
        --exclude-file 26-27/exclusiones.txt --history 26-27/disponibilidad.csv \\
        --rivals-season 26-27 --shortlist-out mide.csv
"""

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import archetypes as arch  # noqa: E402
import paths  # noqa: E402
from tiers import MAX_PICK_PRICE, pick_value  # noqa: E402

from packages.biwenger_tools.api.logic.draft import (  # noqa: E402
    draft_composition_reachable,
)
from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID  # noqa: E402
from packages.biwenger_tools.constants import DRAFT_ORDER_NAMES  # noqa: E402

_LINE_ID = {"PT": GK, "DF": DEF, "MC": MID, "DL": FWD}
SLOTS = 15
# Kept back for every slot still to fill but the reserve keeper's: the bench
# plays (backtest, 26-27), so it is bought, not scraped together at 0.15M.
# Reserving only while more than four slots remained left 0.3 points a round
# on the bench in the 22/10 mock.
DEPTH_RESERVE = 1_200_000
# A substitute below this many points per round is a hole, not cover.
BENCH_FLOOR = 2.5
# A line's soft target: an XI of 4-4-2 plus its bench.
TARGET = {"PT": 2, "DF": 5, "MC": 5, "DL": 3}


def _elig(r):
    return frozenset(_LINE_ID[line] for line in r["lines"] if line in _LINE_ID)


class _Draft:
    def __init__(self, rows, order, budget):
        self.rows = rows
        self.budget = budget
        self.squads = {m: [] for m in order}
        self.spent = {m: 0 for m in order}
        self.taken = set()
        self.cheapest = min(r["price"] for r in rows)

    def feasible(self, manager, r):
        left = SLOTS - len(self.squads[manager]) - 1
        if self.spent[manager] + r["price"] + left * self.cheapest > self.budget:
            return False
        held = [_elig(x) for x in self.squads[manager]]
        return draft_composition_reachable(held + [_elig(r)], left)

    def pool(self, manager):
        return [
            r
            for r in self.rows
            if r["name"] not in self.taken and self.feasible(manager, r)
        ]

    def take(self, manager, r):
        self.taken.add(r["name"])
        self.squads[manager].append(r)
        self.spent[manager] += r["price"]


def rival_pick(pool, target_price):
    """Best projected player within 0.6-1.4× what he spent in this round."""
    band = [r for r in pool if 0.6 * target_price <= r["price"] <= 1.4 * target_price]
    return max(band or pool, key=lambda r: r["pr"])


def _good_floor(rows):
    """Per line, the points per round of the 14th best: tiers A and B."""
    out = {}
    for line in arch.POS:
        prs = sorted((r["pr"] for r in rows if r["pos"] == line), reverse=True)
        out[line] = prs[min(13, len(prs) - 1)] if prs else 0
    return out


def my_pick(draft, me, pick, mine, history, good):
    squad = draft.squads[me]
    have = Counter(r["pos"] for r in squad)
    left = SLOTS - len(squad)
    nxt = next((s for s in mine if s > pick), None)
    gone = Counter(h["line"] for h in history if nxt and pick < h["pick"] < nxt)
    reserve = max(0, left - 2) * DEPTH_RESERVE + (draft.cheapest if left > 1 else 0)
    cap = min(MAX_PICK_PRICE, draft.budget - draft.spent[me] - reserve)
    pool = [r for r in draft.pool(me) if r["price"] <= cap] or draft.pool(me)
    keepers = [r for r in pool if r["pos"] == "PT"]
    if have["PT"] >= 1 and left == 1 and keepers:
        return min(keepers, key=lambda r: r["price"]), "portero suplente, el más barato"
    if have["PT"] >= 1 and left > 1:
        pool = [r for r in pool if r["pos"] != "PT"] or pool
    urgent = []
    for line in arch.POS:
        need = (1 if line == "PT" else TARGET[line]) - have[line]
        if need <= 0:
            continue
        options = [r for r in pool if r["pos"] == line and r["pr"] >= good[line]]
        if options:
            urgent.append((len(options) - gone.get(line, 0) - 2 * need, line, options))
    if urgent:
        _, line, options = min(urgent, key=lambda t: t[0])
        why = (
            f"{arch.POS[line]}: quedan {len(options)} buenos y se irían "
            f"~{gone.get(line, 0)} antes de tu pick {nxt}"
        )
        return max(options, key=pick_value), why
    playing = [r for r in pool if r["pr"] >= BENCH_FLOOR] or pool
    return max(playing, key=pick_value), "banquillo que juega, por valor"


def simulate(rows, order, me, budget, habits, history):
    """`(squads, log)` of a snake draft; `log` is `(pick, round, manager,
    row, reason)`."""
    draft = _Draft(rows, order, budget)
    good = _good_floor(rows)
    mine = arch.my_picks(order.index(me) + 1, len(order), SLOTS)
    log = []
    pick = 0
    for rnd in range(1, SLOTS + 1):
        for manager in order if rnd % 2 else order[::-1]:
            pick += 1
            if manager == me:
                r, why = my_pick(draft, me, pick, mine, history, good)
            else:
                target = habits.get(manager, {}).get(rnd) or 1_000_000
                r, why = rival_pick(draft.pool(manager), target), ""
            draft.take(manager, r)
            log.append((pick, rnd, manager, r, why))
    return draft.squads, log


def season_points(squad):
    """`(eleven + captain, fifteen)` in projected season points."""
    by_line = {
        c: [{**x, "sf": round(x["pr"] * 38)} for x in squad if x["pos"] == c]
        for c in arch.POS
    }
    _, xi, _, dur = arch.lineup(by_line)
    eleven = sum(x["sf"] for x in xi) + (dur["sf"] if dur else 0)
    return round(eleven), round(sum(x["pr"] * 38 for x in squad))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--season", default="26-27")
    ap.add_argument("--ranked", default="")
    ap.add_argument("--real-points", default="")
    ap.add_argument("--exclude-file", default="")
    ap.add_argument("--history", required=True, help="disponibilidad.csv anterior")
    ap.add_argument("--rivals-season", required=True, help="picks de Firestore")
    ap.add_argument("--me", default="Jorge")
    ap.add_argument("--budget", type=float, default=50, help="en millones")
    ap.add_argument("--shortlist-out", default="", help="tus sin medir, en CSV")
    ap.add_argument("--out", default="", help="por defecto <temporada>/ensayo.md")
    args = ap.parse_args()

    ranked = args.ranked or paths.season_path(args.season, paths.RANKED)
    excluded = arch.read_exclusions(args.exclude_file)[0] if args.exclude_file else []
    rows, _, _ = arch.load(ranked, excluded)
    if args.real_points:
        arch.apply_real_points(
            rows,
            arch.read_real_points(args.real_points),
            new=arch.read_no_primera(args.real_points),
        )
    rounds = max((r.get("rounds") or 0 for r in rows), default=0) or 38
    for r in rows:
        r["pr"] = r["sf"] / rounds
    with open(args.history, encoding="utf-8") as fh:
        history = [
            {"pick": int(r["pick"]), "line": r["line"]} for r in csv.DictReader(fh)
        ]
    from board import load_picks

    habits = defaultdict(dict)
    for p in load_picks(args.rivals_season):
        habits[p["manager_name"]][p["round"]] = p["price"]
    order = list(DRAFT_ORDER_NAMES)
    squads, log = simulate(
        rows, order, args.me, int(args.budget * 1_000_000), habits, history
    )

    out = [f"# Ensayo de draft — {args.season}\n", "## Tus picks\n"]
    out.append(
        "| Ronda | Pick | Pos | Jugador | Equipo | Precio | Pts/jor | Fuente "
        "| Por qué |"
    )
    out.append("|--:|--:|:-:|---|---|--:|--:|:-:|---|")
    for pick, rnd, manager, r, why in log:
        if manager == args.me:
            out.append(
                f"| {rnd} | {pick} | {arch.POS[r['pos']]} | {r['name']} | {r['team']} "
                f"| {r['price'] / 1e6:.2f}M | {r['pr']:.1f} | {arch.source_cell(r)} "
                f"| {why} |"
            )
    out += ["", "## La liga simulada\n", "| Mánager | Once + © | Quince | Gasto |"]
    out.append("|---|--:|--:|--:|")
    table = sorted(
        ((season_points(squads[m]), m) for m in order), key=lambda t: -t[0][0]
    )
    for (eleven, fifteen), m in table:
        spent = sum(r["price"] for r in squads[m])
        out.append(f"| {m} | {eleven} | {fifteen} | {spent / 1e6:.2f}M |")
    pending = [
        r["name"]
        for r in squads[args.me][:-1]
        if r.get("source") != "real" and not r.get("no_primera")
    ]
    out += ["", f"**Sin medir en tu quince: {len(pending)}** — {', '.join(pending)}"]
    if args.shortlist_out:
        with open(args.shortlist_out, "w", encoding="utf-8") as fh:
            fh.write("name\n" + "\n".join(pending) + "\n")
        out.append(f"→ `{args.shortlist_out}` para `fetch_real_points`.")

    destination = args.out or paths.season_path(args.season, "ensayo.md")
    with open(destination, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\nEscrito: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
