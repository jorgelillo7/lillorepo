"""Draft — archetype generator.

Reads a ranked CSV (the Phase A output of draft_ranking.py) and builds several
squad-construction archetypes under the budget + composition rules, each with
its best **captain** worked out under the league's hard cap:

  Biwenger rejects any captain whose cf-base price is >= 3M (the captaincy
  doubles points, so the captain is the most valuable roster slot). Prices move
  daily, so a captain pegged at 2.9M can cross 3M after one good match — prefer
  a durable one with a buffer (<= 2.5M) and a modest value-per-M (a screaming
  bargain rockets past 3M fast).

Effective season points are ranked as `total_sf + captain_sf` (the captain's
score counts twice). Prints a comparison and writes a markdown report.

    PYTHONPATH not needed. Run:
      python3 .claude/skills/draft/scripts/archetypes.py --ranked draft-ranked.csv
"""

import argparse
import csv
import unicodedata

POS = {"PT": "POR", "DF": "DEF", "MC": "MED", "DL": "DEL"}
NEED = {"PT": 2, "DF": 5, "MC": 5, "DL": 3}
CAPTAIN_CAP = 3_000_000
CAPTAIN_SAFE = 2_500_000  # durable buffer below the cap


def _norm(s):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )


def load(path, exclude):
    ban = {_norm(x) for x in exclude if x}
    rows = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["no_jp_data"] == "True" or not r["sofascore"] or not r["price"]:
                continue
            price = int(r["price"])
            if price <= 0 or _norm(r["name"]) in ban:
                continue
            rows.append(
                {
                    "name": r["name"],
                    "team": r["team"],
                    "pos": r["position"],
                    "sf": int(r["sofascore"]),
                    "price": price,
                    "vm": float(r["value_per_m"]) if r["value_per_m"] else 0.0,
                }
            )
    return rows


def build(rows, budget, forced=(), band=None):
    """Force `forced` (names), fill the cheapest per line from the (optionally
    band-restricted) pool, then greedily upgrade non-forced picks to spend the
    budget while maximising SofaScore."""
    byp = {
        c: sorted([r for r in rows if r["pos"] == c], key=lambda x: -x["sf"])
        for c in POS
    }
    forced_n = {_norm(f) for f in forced}
    squad = {c: [] for c in POS}
    used = set()
    spent = 0
    for f in forced:
        for c in POS:
            m = [r for r in byp[c] if _norm(r["name"]) == _norm(f)]
            if m:
                squad[c].append(m[0])
                used.add(m[0]["name"])
                spent += m[0]["price"]
    for c in POS:
        pool = [r for r in byp[c] if band is None or band[0] <= r["price"] <= band[1]]
        cheap = sorted(
            [r for r in pool if r["name"] not in used], key=lambda x: x["price"]
        )
        while len(squad[c]) < NEED[c] and cheap:
            pk = cheap.pop(0)
            squad[c].append(pk)
            used.add(pk["name"])
            spent += pk["price"]
    improved = True
    while improved:
        improved = False
        best = None
        for c in POS:
            pool = [
                r for r in byp[c] if band is None or band[0] <= r["price"] <= band[1]
            ]
            for i, cur in enumerate(squad[c]):
                if _norm(cur["name"]) in forced_n:
                    continue
                for cand in pool:
                    if cand["name"] in used:
                        continue
                    extra = cand["price"] - cur["price"]
                    gain = cand["sf"] - cur["sf"]
                    if gain > 0 and spent + extra <= budget:
                        eff = gain / max(extra, 1)
                        if best is None or eff > best[0]:
                            best = (eff, c, i, cur, cand, extra)
        if best:
            _, c, i, cur, cand, extra = best
            used.discard(cur["name"])
            used.add(cand["name"])
            squad[c][i] = cand
            spent += extra
            improved = True
    return squad, spent


def captain(squad):
    """Best durable captain, tiered: (1) durable — <=2.5M and not a rocket
    (v/M<=200); (2) any <=2.5M (flag rocket — will cross 3M fast); (3) any <3M
    (flag fragile — pegged at the cap). Prices move daily, so durability beats a
    marginally higher SF. Returns (player, note) or (None, reason)."""
    elig = [r for c in POS for r in squad[c] if r["price"] < CAPTAIN_CAP]
    if not elig:
        return None, "SIN CAPITÁN — ningún jugador <3M (tiras el bonus)"
    durable = [r for r in elig if r["price"] <= CAPTAIN_SAFE and r["vm"] <= 200]
    safe = [r for r in elig if r["price"] <= CAPTAIN_SAFE]
    pool = durable or safe or elig
    cap = max(pool, key=lambda r: r["sf"])
    rise = (
        "🚀 sube rápido"
        if cap["vm"] > 200
        else ("↗ sube" if cap["vm"] > 130 else "estable")
    )
    if cap in durable:
        warn = "✅ durable"
    elif cap in safe:
        warn = "⚠️ chollo que se dispara — durará poco elegible"
    else:
        warn = "⚠️ pegado al cap (>2.5M) — frágil"
    return cap, f"{cap['price'] / 1e6:.2f}M · v/M {cap['vm']:.0f} ({rise}) · {warn}"


def total_sf(squad):
    return sum(r["sf"] for c in POS for r in squad[c])


def render(name, desc, squad, spent):
    cap, capnote = captain(squad)
    eff = total_sf(squad) + (cap["sf"] if cap else 0)
    o = [f"## {name}", f"_{desc}_", ""]
    o.append(
        f"**SF total {total_sf(squad)} · gasto {spent / 1e6:.2f}M · "
        f"capitán {cap['name'] + ' ' + str(cap['sf']) if cap else '—'} → "
        f"efectivo {eff}**"
    )
    o.append(f"Capitán: {capnote}\n")
    o.append("| Pos | Jugador | Equipo | Precio | SF | Valor/M | © |")
    o.append("|---|---|---|--:|--:|--:|:-:|")
    for c in ("PT", "DF", "MC", "DL"):
        for r in sorted(squad[c], key=lambda x: -x["sf"]):
            mark = "©" if cap and r["name"] == cap["name"] else ""
            o.append(
                f"| {POS[c]} | {r['name']} | {r['team']} | {r['price'] / 1e6:.2f}M "
                f"| {r['sf']} | {r['vm']:.0f} | {mark} |"
            )
    o.append("")
    return "\n".join(o), eff


def main():
    ap = argparse.ArgumentParser(description="Draft archetype generator")
    ap.add_argument("--ranked", required=True, help="ranked CSV from draft_ranking.py")
    ap.add_argument("--budget", type=float, default=52.0, help="budget in millions")
    ap.add_argument("--exclude", default="", help="comma-separated names to ban (news)")
    ap.add_argument("--out", default="mi-arquetipos.md")
    args = ap.parse_args()

    rows = load(args.ranked, args.exclude.split(","))
    budget = int(args.budget * 1_000_000)
    top = sorted(rows, key=lambda x: -x["sf"])
    anchors = [r["name"] for r in top if 6_000_000 <= r["price"] <= 12_000_000][:3]
    # Best durable captain in the whole pool (2.0-2.5M, not a rocket): the
    # captain-anchor archetype forces him so the © slot survives price drift.
    durable = [
        r for r in top if 2_000_000 <= r["price"] <= CAPTAIN_SAFE and r["vm"] <= 200
    ]
    cap_anchor = durable[0]["name"] if durable else top[-1]["name"]

    specs = [
        ("Value-max (reparto)", "Sin anclas caras: pura eficiencia, máximo SF.", {}),
        (
            "Capitán-ancla",
            f"Value-max + capitán durable fijo ({cap_anchor}).",
            {"forced": [cap_anchor]},
        ),
        ("Columna vertebral", "2-3 studs de valor + chollos.", {"forced": anchors}),
        (
            "Superestrella",
            "El mejor galáctico + relleno.",
            {"forced": [top[0]["name"]]},
        ),
        (
            "2 galácticos + despojos",
            "Los dos más caros + mínimos.",
            {"forced": [top[0]["name"], top[1]["name"]]},
        ),
        (
            "Ultra equilibrio (3-4M)",
            "Todos en banda 3-4M (ojo capitán).",
            {"band": (3_000_000, 4_500_000)},
        ),
    ]
    blocks = []
    ranking = []
    for name, desc, kw in specs:
        squad, spent = build(rows, budget, **kw)
        block, eff = render(name, desc, squad, spent)
        blocks.append(block)
        ranking.append((eff, name))

    ranking.sort(reverse=True)
    header = [
        "# Arquetipos de draft — comparativa\n",
        "Puntos **efectivos** = SF total + SF del capitán (el capitán dobla, "
        "cap 3M). Ordenado por efectivo:\n",
        "| # | Arquetipo | Efectivo |",
        "|--:|---|--:|",
    ]
    for i, (eff, name) in enumerate(ranking, 1):
        header.append(f"| {i} | {name} | {eff} |")
    header.append(
        f"\n> 🏆 **Recomendación: {ranking[0][1]}** ({ranking[0][0]} efectivo)\n"
    )

    report = "\n".join(header) + "\n" + "\n".join(blocks) + "\n"
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(report)
    print("\n".join(header))
    print("Escrito:", args.out)


if __name__ == "__main__":
    main()
