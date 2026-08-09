"""Draft — mid-draft board: what you hold, what you can still spend, who is free.

The decision sheet is written once and rots as the others pick. This recomputes
it against Firestore, the only record of who is actually gone.

Read-only: `draft/{season}/picks` and the ranked CSV.

    PYTHONPATH=. python3 .claude/skills/draft/scripts/board.py \
        --season 26-27 --me Jorge --ranked draft-ranked.csv \
        --real-points draft-real-points.csv --budget 52

Without `--real-points` the ordering is JP's projection, which is SofaScore and
not what this league scores.
"""

import argparse
import csv
import sys
import unicodedata
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from archetypes import BANDS, NEED, POS, eligibility, price_band  # noqa: E402

from packages.biwenger_tools.api.logic.draft import composition_ok  # noqa: E402
import paths  # noqa: E402

from packages.biwenger_tools.constants import DRAFT_ORDER_NAMES  # noqa: E402

# Median measured `real/projection`. Orders a list; does not compare magnitudes
# across players — the ratio ranges from 0.225 to 0.610.
GLOBAL_FACTOR = 0.404


def _norm(s):
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _eur(amount):
    return f"{(amount or 0) / 1_000_000:.2f}M".replace(".", ",")


def my_picks(position, managers, rounds):
    """Your global pick numbers in a `managers` x `rounds` snake."""
    out = []
    for rnd in range(1, rounds + 1):
        slot = position if rnd % 2 else managers - position + 1
        out.append((rnd - 1) * managers + slot)
    return out


def load_picks(season):
    # Imported here so the pure helpers stay usable — and testable — without
    # the Firestore client and its credentials.
    from core.sdk import firestore as fs

    return sorted(
        (
            p
            for p in fs.query(f"draft/{season}/picks")
            if p.get("status") == "applied" and p.get("global_pick")
        ),
        key=lambda p: p["global_pick"],
    )


def load_market(path):
    """`normalised name -> row` for every priced, scored player."""
    market = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not r["price"] or not r["sofascore"]:
                continue
            market[_norm(r["name"])] = {
                "name": r["name"],
                "team": r["team"],
                "pos": r["position"],
                "price": int(r["price"]),
                "sf": int(r["sofascore"]),
                "placeholder": r.get("jp_placeholder") == "True",
                "lines": (r.get("alt_positions") or r["position"]).split("/"),
                "real": None,
                "starts": None,
            }
    return market


def points(row):
    """`(points, badge)` on the league scale, measured or projected.

    A player carrying JP's default score has no projection to calibrate, so he
    is returned unscored rather than with a number that means nothing.
    """
    if row["real"] is not None:
        return row["real"], "✅"
    if row["placeholder"]:
        return None, "🎲"
    return round(row["sf"] * GLOBAL_FACTOR), "~"


def overlay_real(market, path):
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            row = market.get(_norm(r["name"]))
            if row and r.get("points"):
                row["real"] = int(r["points"])
                row["starts"] = int(r.get("starts") or 0)


def board_state(market, picks):
    """`(free rows, taken names)` — the market split by what has happened."""
    taken = {_norm(p.get("player_name")) for p in picks}
    free = [r for k, r in market.items() if k not in taken]
    return free, taken


def spend_cap(free, held, line, budget_left):
    """Most you can pay for `line` and still fill every other empty slot.

    The trap this exists for: with four picks left and 3M, a 2.55M forward
    looks affordable and is not — the other three slots still have to be paid
    for. Reserves the cheapest available player per remaining mandatory slot.

    A multi-position player counts towards every line he covers, so a squad
    that looks short of defenders may not be — reserving against the naive
    per-line count would refuse purchases that are perfectly affordable.
    """
    covered = {code: 0 for code in POS}
    for code, rows in held.items():
        for entry in rows:
            row = entry[1] if isinstance(entry, tuple) else entry
            for other in row.get("lines", [code]) if row else [code]:
                if other in covered:
                    covered[other] += 1
    reserve = 0
    for other in POS:
        if other == line:
            continue
        gap = max(0, NEED[other] - covered[other])
        prices = sorted(r["price"] for r in free if other in r.get("lines", [r["pos"]]))
        reserve += sum(prices[:gap])
    return budget_left - reserve


def availability(market, picks, line, band):
    """`(free, supply)` for that line and band right now.

    Counted against the market, not against the players who end up drafted: a
    band nobody buys is fully available, and dividing by the drafted count
    reports it as exhausted.
    """
    supply = [
        r
        for r in market.values()
        if r["pos"] == line and price_band(r["price"]) == band
    ]
    if not supply:
        return None
    taken = {_norm(p.get("player_name")) for p in picks}
    left = [r for r in supply if _norm(r["name"]) not in taken]
    return len(left), len(supply)


def main():
    ap = argparse.ArgumentParser(description="Estado del draft a mitad de camino")
    ap.add_argument("--season", default="26-27")
    ap.add_argument("--me", default="Jorge")
    ap.add_argument(
        "--ranked", default="", help="por defecto <temporada>/draft-ranked.csv"
    )
    ap.add_argument("--real-points", default="")
    ap.add_argument("--budget", type=float, default=52, help="en millones")
    ap.add_argument("--managers", type=int, default=len(DRAFT_ORDER_NAMES))
    ap.add_argument("--rounds", type=int, default=15)
    ap.add_argument("--top", type=int, default=12, help="candidatos por línea")
    args = ap.parse_args()

    order = [_norm(n) for n in DRAFT_ORDER_NAMES]
    position = order.index(_norm(args.me)) + 1

    picks = load_picks(args.season)
    ranked = args.ranked or paths.season_path(args.season, paths.RANKED)
    market = load_market(ranked)
    if args.real_points:
        overlay_real(market, args.real_points)

    mine = [p for p in picks if _norm(p.get("manager_name")) == _norm(args.me)]
    spent = sum(p.get("price") or 0 for p in mine)
    budget = int(args.budget * 1_000_000)
    slots = my_picks(position, args.managers, args.rounds)
    done = {p["global_pick"] for p in mine}
    pending = [s for s in slots if s not in done]
    last = picks[-1]["global_pick"] if picks else 0

    print(f"# Draft {args.season} — {args.me} (posición {position}/{args.managers})\n")
    who = picks[-1].get("manager_name") if picks else "—"
    print(f"Van {len(picks)} picks. El último fue el {last} ({who}).\n")

    by_line = defaultdict(list)
    for p in mine:
        row = market.get(_norm(p.get("player_name")))
        by_line[row["pos"] if row else "?"].append((p, row))
    print(f"## Tu plantilla — {len(mine)}/{args.rounds}\n")
    print("| Pick | Pos | Jugador | Equipo | Precio | Pts |")
    print("|--:|:-:|---|---|--:|--:|")
    for p in mine:
        row = market.get(_norm(p.get("player_name")))
        pts, mark = points(row) if row else (None, "?")
        print(
            f"| {p['global_pick']} | {POS.get(row and row['pos'], '?')} "
            f"| {p.get('player_name')} | {p.get('player_team', '—')} "
            f"| {_eur(p.get('price'))} | {pts if pts is not None else '—'} {mark} |"
        )
    print(
        f"\n**Gastado {_eur(spent)} de {_eur(budget)} · quedan {_eur(budget - spent)}**"
    )
    print(f"**Picks pendientes: {', '.join(map(str, pending)) or 'ninguno'}**\n")

    print("## Composición\n")
    print("| Línea | De su línea | Contando multiposición | Mínimo |")
    print("|---|--:|--:|--:|")
    held_rows = [row for rows in by_line.values() for _, row in rows if row]
    for code in POS:
        strict = len(by_line.get(code, []))
        loose = sum(1 for r in held_rows if code in r.get("lines", [r["pos"]]))
        print(f"| {POS[code]} | {strict} | **{loose}** | {NEED[code]} |")
    legal = composition_ok([eligibility(r) for r in held_rows])
    print(
        "\n"
        + (
            "✅ Ya puedes alinear un once legal."
            if legal
            else "⚠️ Todavía no puedes alinear un once legal."
        )
    )
    print(
        "\n«Contando multiposición» es lo que de verdad limita: un DF/MC tapa "
        "las dos líneas, así que ir corto en una columna no significa ir corto "
        "de verdad.\n"
    )

    free, _ = board_state(market, picks)
    left_budget = budget - spent
    print("## Qué queda en cada banda (oferta real, no la drafteada)\n")
    print("| Línea | " + " | ".join(label for _, label in BANDS) + " |")
    print("|---" * (len(BANDS) + 1) + "|")
    for code in POS:
        cells = []
        for _, label in BANDS:
            got = availability(market, picks, code, label)
            cells.append(f"{got[0]}/{got[1]}" if got else "—")
        print(f"| {POS[code]} | " + " | ".join(cells) + " |")
    print("\n`libres/total` del mercado, ahora mismo.\n")

    print(f"## Libres que te caben ({_eur(left_budget)} para {len(pending)} fichas)\n")
    for code in POS:
        gap = max(0, NEED[code] - len(by_line.get(code, [])))
        cap = spend_cap(free, by_line, code, left_budget)
        pool = [r for r in free if r["pos"] == code and r["price"] <= cap]
        # Placeholders last: JP's default score is a top-decile number on a
        # 1.5M player, so ranking it inline hijacks the head of the list.
        pool.sort(key=lambda r: (r["placeholder"], -(points(r)[0] or 0)))
        head = f"### {POS[code]}"
        if gap:
            head += f" — te faltan {gap}"
        print(f"{head} · tope {_eur(cap)}\n")
        print("| Jugador | Equipo | Precio | Pts | Fuente |")
        print("|---|---|--:|--:|:-:|")
        for r in pool[: args.top]:
            pts, mark = points(r)
            print(
                f"| {r['name']} | {r['team']} | {_eur(r['price'])} "
                f"| {pts if pts is not None else '—'} | {mark} |"
            )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
