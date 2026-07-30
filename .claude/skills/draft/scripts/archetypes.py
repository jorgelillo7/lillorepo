"""Draft — archetype generator.

Reads a ranked CSV (the Phase A output of draft_ranking.py) and builds several
squad-construction archetypes under the budget + composition rules, each scored
by the points it can actually field:

  The captain doubles points, and Biwenger rejects any captain whose cf-base
  price is >= 3M, so the sub-3M slot is the most valuable one on the roster. Two
  constraints make the naive "best sub-3M player" wrong: the captain must be in
  the XI (production does the same, `lineup._CAPTAIN_MAX_PRICE`), and prices move
  daily, so a captain pegged near the cap or priced as a screaming bargain loses
  eligibility within weeks.

Archetypes are therefore ranked by **durable effective points** — squad SF plus
the SF of the best captain that both starts and survives price drift. Raw
effective points (any eligible captain) are reported alongside as the optimistic
bound.

    PYTHONPATH not needed. Run:
      python3 .claude/skills/draft/scripts/archetypes.py --ranked draft-ranked.csv
"""

import argparse
import csv
import statistics
import unicodedata
from collections import Counter

POS = {"PT": "POR", "DF": "DEF", "MC": "MED", "DL": "DEL"}
NEED = {"PT": 2, "DF": 5, "MC": 5, "DL": 3}
CAPTAIN_CAP = 3_000_000
CAPTAIN_SAFE = 2_500_000  # durable buffer below the cap
ROCKET_VM = 200  # above this value-per-M a cheap player rockets past the cap

# (DF, MC, DL) — the XI shapes Biwenger accepts, all fieldable from a 2-5-5-3.
FORMATIONS = (
    (3, 4, 3),
    (3, 5, 2),
    (4, 3, 3),
    (4, 4, 2),
    (4, 5, 1),
    (5, 3, 2),
    (5, 4, 1),
)
TIER_RANK = {"durable": 0, "safe": 1, "fragile": 2}


def _norm(s):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )


def tier(r):
    """Captain durability tier, or None when the player is over the 3M cap."""
    if r["price"] >= CAPTAIN_CAP:
        return None
    if r["price"] <= CAPTAIN_SAFE:
        return "durable" if r["vm"] <= ROCKET_VM else "safe"
    return "fragile"


def detect_placeholder(scores):
    """The SF value JP hands out to players it cannot rate (promoted clubs, new
    signings). Shows up as a spike on one exact value well above the median;
    returns None when no such spike exists."""
    counts = Counter(scores)
    med = statistics.median(scores)
    for value, n in counts.most_common(5):
        if n < 5 or value <= med:
            continue
        window = [counts.get(v, 0) for v in range(value - 15, value + 16) if v != value]
        if n > 4 * (sum(window) / len(window)):
            return value
    return None


def load(path, exclude, placeholder_sf=None, keep_placeholder=False):
    """Rows usable by the optimiser, plus the placeholder SF that was applied.
    Players carrying the placeholder score have no real data and are dropped
    unless `keep_placeholder`."""
    ban = {_norm(x) for x in exclude if x}
    raw = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["no_jp_data"] == "True" or not r["sofascore"] or not r["price"]:
                continue
            price = int(r["price"])
            if price <= 0 or _norm(r["name"]) in ban:
                continue
            raw.append(
                {
                    "name": r["name"],
                    "team": r["team"],
                    "pos": r["position"],
                    "sf": int(r["sofascore"]),
                    "price": price,
                    "vm": float(r["value_per_m"]) if r["value_per_m"] else 0.0,
                }
            )
    if placeholder_sf is None:
        placeholder_sf = detect_placeholder([r["sf"] for r in raw])
    dropped = [r for r in raw if placeholder_sf and r["sf"] == placeholder_sf]
    if keep_placeholder:
        dropped = []
    kept = [r for r in raw if r not in dropped]
    return kept, placeholder_sf, dropped


def build(rows, budget, forced=(), band=None, thin_bench=False):
    """Force `forced` (names), fill the cheapest per line from the (optionally
    band-restricted) pool, then greedily upgrade non-forced picks to spend the
    budget while maximising SofaScore. Returns (squad, spent, warnings).

    `thin_bench` freezes the cheapest pick of every line at floor price, so the
    budget goes to the eleven. Only the eleven score on a matchday, so a euro
    spent on a substitute buys cover for absences, not points.
    """
    byp = {
        c: sorted([r for r in rows if r["pos"] == c], key=lambda x: -x["sf"])
        for c in POS
    }
    forced_n = {_norm(f) for f in forced}
    squad = {c: [] for c in POS}
    used = set()
    spent = 0
    warnings = []
    for f in forced:
        pick = next(
            (r for c in POS for r in byp[c] if _norm(r["name"]) == _norm(f)), None
        )
        if pick is None or pick["name"] in used:
            continue
        if len(squad[pick["pos"]]) >= NEED[pick["pos"]]:
            warnings.append(f"{f}: línea {POS[pick['pos']]} llena, no forzado")
            continue
        if spent + pick["price"] > budget:
            warnings.append(f"{f}: no cabe en presupuesto, no forzado")
            continue
        squad[pick["pos"]].append(pick)
        used.add(pick["name"])
        spent += pick["price"]
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
        if len(squad[c]) < NEED[c]:
            warnings.append(f"{POS[c]}: solo {len(squad[c])}/{NEED[c]} jugadores")
    if spent > budget:
        warnings.append(f"relleno mínimo ya excede el presupuesto ({spent / 1e6:.2f}M)")
    # The frozen substitute of each line: the cheapest pick, left untouched by
    # the hill-climb so its money goes to the eleven instead.
    frozen = set()
    if thin_bench:
        for c in POS:
            free = [r for r in squad[c] if _norm(r["name"]) not in forced_n]
            if free:
                frozen.add(min(free, key=lambda r: r["price"])["name"])

    improved = True
    while improved:
        improved = False
        best = None
        for c in POS:
            pool = [
                r for r in byp[c] if band is None or band[0] <= r["price"] <= band[1]
            ]
            for i, cur in enumerate(squad[c]):
                if _norm(cur["name"]) in forced_n or cur["name"] in frozen:
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
    return squad, spent, warnings


def _xi(squad, formation):
    counts = dict(zip(("DF", "MC", "DL"), formation), PT=1)
    return [
        r
        for c in POS
        for r in sorted(squad[c], key=lambda x: -x["sf"])[: counts.get(c, 0)]
    ]


def lineup(squad):
    """Best XI and its captain. Picks the formation that maximises XI SF plus a
    fieldable durable captain, then the captain within it (durable > safe >
    fragile, best SF inside the tier). Returns (formation, xi, captain,
    durable_captain) — either captain may be None."""
    best = None
    for formation in FORMATIONS:
        xi = _xi(squad, formation)
        if len(xi) < 11:
            continue
        elig = [r for r in xi if tier(r)]
        cap = min(elig, key=lambda r: (TIER_RANK[tier(r)], -r["sf"]), default=None)
        durables = [r for r in xi if tier(r) == "durable"]
        dur = max(durables, key=lambda r: r["sf"], default=None)
        score = sum(r["sf"] for r in xi) + (dur["sf"] if dur else 0)
        if best is None or score > best[0]:
            best = (score, formation, xi, cap, dur)
    return best[1:] if best else (None, [], None, None)


def total_sf(squad):
    return sum(r["sf"] for c in POS for r in squad[c])


def durable_eff(squad):
    _, _, _, dur = lineup(squad)
    return total_sf(squad) + (dur["sf"] if dur else 0)


def repair_captain(squad, spent, rows, budget, forced):
    """Swap one non-forced pick for the durable captain that best raises durable
    effective points. No-op when the squad can already field one. Returns
    (squad, spent, note)."""
    if lineup(squad)[3] is not None:
        return squad, spent, None
    forced_n = {_norm(f) for f in forced}
    in_squad = {r["name"] for c in POS for r in squad[c]}
    cands = sorted(
        (r for r in rows if tier(r) == "durable" and r["name"] not in in_squad),
        key=lambda r: -r["sf"],
    )[:30]
    base = durable_eff(squad)
    best = None
    for cand in cands:
        c = cand["pos"]
        for i, cur in enumerate(squad[c]):
            if _norm(cur["name"]) in forced_n:
                continue
            new_spent = spent - cur["price"] + cand["price"]
            if new_spent > budget:
                continue
            trial = {k: list(v) for k, v in squad.items()}
            trial[c][i] = cand
            gain = durable_eff(trial) - base
            if gain > 0 and (best is None or gain > best[0]):
                best = (gain, trial, new_spent, cur, cand)
    if not best:
        return squad, spent, None
    _, trial, new_spent, cur, cand = best
    return trial, new_spent, f"🔧 capitán reparado: {cur['name']} → {cand['name']}"


def _alternatives(options):
    """The runners-up, so a human can override on news the data cannot see."""
    if len(options) < 2:
        return ""
    alts = ", ".join(
        f"{c['name']} ({c['price'] / 1e6:.2f}M, {score})" for score, c in options[1:3]
    )
    return f"Alternativas equivalentes: {alts}."


def my_picks(position, managers, rounds):
    """Global pick numbers for `position` in a snake draft, in order.

    Round order reverses every round, so the gaps alternate — picking third of
    seven means waiting 9 picks, then 5, then 9 again. That gap is why the plan
    matters: whoever you do not take now may not survive to your next turn.
    """
    if not position:
        return []
    picks = []
    for r in range(rounds):
        idx = position - 1 if r % 2 == 0 else managers - position
        picks.append(r * managers + idx + 1)
    return picks


def best_star(rows, budget, top, thin_bench=False, extra_forced=()):
    """The star that fields the most XI points, not the dearest one.

    The most expensive player eats the budget the other ten starters need, so
    the top of the ranking is usually the wrong forced pick. Tries the best few
    and keeps whichever squad fields most.
    """
    scored = []
    for cand in top[:8]:
        forced = [cand["name"], *extra_forced]
        squad, _, _ = build(rows, budget, forced=forced, thin_bench=thin_bench)
        _, xi, _, dur = lineup(squad)
        score = sum(r["sf"] for r in xi) + (dur["sf"] if dur else 0)
        scored.append((score, cand))
    scored.sort(key=lambda t: -t[0])
    return scored[:3]


def render(name, desc, squad, spent, budget, warnings, pick_numbers=None):
    formation, xi, cap, dur = lineup(squad)
    starters = {r["name"] for r in xi}
    sf = total_sf(squad)
    raw = sf + (cap["sf"] if cap else 0)
    eff = sf + (dur["sf"] if dur else 0)
    xi_eff = sum(r["sf"] for r in xi) + (dur["sf"] if dur else 0)
    shape = "-".join(str(n) for n in formation) if formation else "—"
    o = [f"## {name}", f"_{desc}_", ""]
    o.append(
        f"**Efectivo XI {xi_eff} · SF total {sf} · gasto {spent / 1e6:.2f}M · "
        f"XI 1-{shape} · efectivo durable {eff}** (bruto {raw})"
    )
    if dur:
        o.append(
            f"Capitán ✅ **{dur['name']}** {dur['sf']} · {dur['price'] / 1e6:.2f}M · "
            f"v/M {dur['vm']:.0f} — titular y aguanta la subida de precio."
        )
    elif cap:
        why = (
            "chollo que se dispara — cruzará 3M en semanas"
            if tier(cap) == "safe"
            else "pegado al cap (>2.5M) — un buen partido y queda inelegible"
        )
        o.append(
            f"Capitán ⚠️ **{cap['name']}** {cap['sf']} · {cap['price'] / 1e6:.2f}M · "
            f"v/M {cap['vm']:.0f} — {why}. Sin ancla durable: no cuenta en el efectivo."
        )
    else:
        o.append(
            "Capitán ❌ **ninguno** — sin titular <3M, tiras el bonus cada jornada."
        )
    if spent > budget:
        warnings = warnings + [
            f"excede el presupuesto por {(spent - budget) / 1e6:.2f}M"
        ]
    for w in warnings:
        o.append(f"> ⚠️ {w}")
    o.append("")
    # Draft order: best SofaScore first. Rivals draft on perceived quality, not
    # price — last season a 3.32M Marcos Alonso went tenth overall, ahead of
    # players costing twice as much.
    plan = {}
    if pick_numbers:
        contested = sorted(
            (r for c in POS for r in squad[c]), key=lambda r: (-r["sf"], -r["price"])
        )
        for slot, r in zip(pick_numbers, contested):
            plan[r["name"]] = slot

    head = "| Pick | Pos | Jugador | Equipo | Precio | SF | Valor/M | XI | © |"
    rule = "|--:|---|---|---|--:|--:|--:|:-:|:-:|"
    if not plan:
        head = head.replace("| Pick ", "")
        rule = rule.replace("|--:", "", 1)
    o.append(head)
    o.append(rule)
    for c in ("PT", "DF", "MC", "DL"):
        for r in sorted(squad[c], key=lambda x: -x["sf"]):
            mark = "©" if dur and r["name"] == dur["name"] else ""
            cells = (
                f"| {POS[c]} | {r['name']} | {r['team']} | {r['price'] / 1e6:.2f}M "
                f"| {r['sf']} | {r['vm']:.0f} | {'★' if r['name'] in starters else ''} "
                f"| {mark} |"
            )
            o.append((f"| {plan[r['name']]} " if plan else "") + cells)
    o.append("")
    return "\n".join(o), eff, raw, spent, xi_eff


def main():
    ap = argparse.ArgumentParser(description="Draft archetype generator")
    ap.add_argument("--ranked", required=True, help="ranked CSV from draft_ranking.py")
    ap.add_argument("--budget", type=float, default=52.0, help="budget in millions")
    ap.add_argument("--exclude", default="", help="comma-separated names to ban (news)")
    ap.add_argument(
        "--pick-position",
        type=int,
        default=0,
        help="your slot in the snake order (1-based); adds the pick plan",
    )
    ap.add_argument("--managers", type=int, default=7, help="managers in the draft")
    ap.add_argument(
        "--placeholder-sf",
        type=int,
        default=None,
        help="JP default score for unrated players (auto-detected when omitted)",
    )
    ap.add_argument(
        "--keep-placeholder",
        action="store_true",
        help="keep unrated players instead of dropping them",
    )
    ap.add_argument("--out", default="mi-arquetipos.md")
    args = ap.parse_args()

    rows, placeholder, dropped = load(
        args.ranked,
        args.exclude.split(","),
        args.placeholder_sf,
        args.keep_placeholder,
    )
    if args.budget > 1_000:
        ap.error(
            f"--budget se expresa en millones (52, no {args.budget:.0f}). "
            "Pasar euros multiplica el presupuesto por un millón y el "
            "generador devuelve un 15 imposible sin avisar."
        )
    budget = int(args.budget * 1_000_000)
    top = sorted(rows, key=lambda x: -x["sf"])
    anchors = [r["name"] for r in top if 6_000_000 <= r["price"] <= 12_000_000][:3]

    pick_numbers = my_picks(args.pick_position, args.managers, sum(NEED.values()))

    star_options = best_star(rows, budget, top)
    thin_options = best_star(rows, budget, top, thin_bench=True)
    star = star_options[0][1] if star_options else None
    thin_star = thin_options[0][1] if thin_options else None

    specs = [
        ("Value-max (reparto)", "Sin anclas caras: pura eficiencia, máximo SF.", {}),
        ("Columna vertebral", "2-3 studs de valor + chollos.", {"forced": anchors}),
        (
            "Superestrella",
            f"{star['name']} ({star['price'] / 1e6:.2f}M) + relleno. "
            + _alternatives(star_options),
            {"forced": [star["name"]]},
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
        (
            "Once de gala (banco mínimo)",
            "Suplentes al precio suelo: todo el dinero en los once.",
            {"thin_bench": True},
        ),
    ]
    if thin_star:
        specs.append(
            (
                "Once de gala + estrella",
                f"Banco mínimo con {thin_star['name']} "
                f"({thin_star['price'] / 1e6:.2f}M) arriba. "
                + _alternatives(thin_options),
                {"thin_bench": True, "forced": [thin_star["name"]]},
            )
        )
    blocks = []
    ranking = []
    seen = {}
    for idx, (name, desc, kw) in enumerate(specs):
        squad, spent, warnings = build(rows, budget, **kw)
        if kw.get("band") is None and not kw.get("thin_bench"):
            squad, spent, note = repair_captain(
                squad, spent, rows, budget, kw.get("forced", ())
            )
            if note:
                warnings = warnings + [note]
        sig = frozenset(r["name"] for c in POS for r in squad[c])
        twin = seen.setdefault(sig, name)
        if twin != name:
            warnings = warnings + [f"15 idéntico a «{twin}»"]
        block, eff, raw, spent, xi_eff = render(
            name, desc, squad, spent, budget, warnings, pick_numbers
        )
        blocks.append(block)
        ranking.append((xi_eff, eff, raw, spent, idx, name, twin))

    # Ranked by XI points: only the eleven score on a matchday.
    ranking.sort(key=lambda t: (-t[0], -t[1], t[3], t[4]))
    header = [
        "# Arquetipos de draft — comparativa\n",
        "**Efectivo XI** = SF de los once titulares + SF del capitán. Es la "
        "columna que manda: en Biwenger sólo puntúan los once, así que un euro "
        "gastado en el banquillo compra cobertura ante ausencias, no puntos.\n",
        "**Efectivo durable** suma además los cuatro suplentes — mide el plantel "
        "entero y por eso premia un banco caro que la liga no recompensa. Se "
        "mantiene como referencia de profundidad frente a lesiones y rotaciones.\n",
        "El capitán cuenta sólo si además es titular y aguanta la deriva de "
        "precios (©<3M, ≤2.5M, v/M ≤200); el bruto acepta cualquier capitán "
        "elegible hoy.\n",
        "| # | Arquetipo | Efectivo XI | Efectivo durable | Bruto | Gasto |",
        "|--:|---|--:|--:|--:|--:|",
    ]
    for i, (xi_eff, eff, raw, spent, _, name, twin) in enumerate(ranking, 1):
        label = name if twin == name else f"{name} _(= {twin})_"
        header.append(
            f"| {i} | {label} | {xi_eff} | {eff} | {raw} | {spent / 1e6:.2f}M |"
        )
    header.append(
        f"\n> 🏆 **Recomendación: {ranking[0][5]}** " f"({ranking[0][0]} efectivo XI)\n"
    )
    if placeholder and not args.keep_placeholder:
        names = ", ".join(f"{r['name']} ({r['team']})" for r in dropped)
        header.append(
            f"> ⚠️ **{len(dropped)} jugadores descartados**: JP les asigna "
            f"`SF {placeholder}` por defecto porque no tiene datos suyos "
            f"(ascendidos / fichajes). No son puntos reales. Con "
            f"`--keep-placeholder` entran igualmente: {names}\n"
        )

    report = "\n".join(header) + "\n" + "\n".join(blocks) + "\n"
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(report)
    print("\n".join(header))
    print("Escrito:", args.out)


if __name__ == "__main__":
    main()
