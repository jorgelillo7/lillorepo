"""Draft — closing report: when each kind of player ran out.

Run once, after the draft ends. Answers next year's real question — *«¿en qué
pick tengo que coger portero?»* — with the picks that actually happened instead
of a guess.

Reads `draft/{season}/picks` from Firestore and one public competition payload
(for each player's line); it never touches the per-player endpoint.

Writes `history/{season}.md` (the readable record) and `history/{season}.csv`
(what `archetypes.py --history` reads) unless told otherwise.

    PYTHONPATH=. python3 .claude/skills/draft/scripts/availability_report.py \
        --season 26-27
"""

import argparse
import os
from collections import defaultdict

import requests

from core.sdk import firestore as fs

COMPETITION_URL = "https://cf.biwenger.com/api/v2/competitions/la-liga/data?lang=es"
# Without a browser User-Agent the endpoint answers JSONP, not JSON.
HEADERS = {"User-Agent": "Mozilla/5.0"}
LINES = [("PT", "Porteros"), ("DF", "Defensas"), ("MC", "Medios"), ("DL", "Delanteros")]
POSITION_CODE = {1: "PT", 2: "DF", 3: "MC", 4: "DL"}
BANDS = ((6_000_000, "≥ 6M"), (3_000_000, "3–6M"), (1_500_000, "1,5–3M"), (0, "< 1,5M"))


def _band(price: int) -> str:
    for floor, label in BANDS:
        if price >= floor:
            return label
    return "< 1,5M"


def _eur(amount) -> str:
    return f"{(amount or 0) / 1_000_000:.2f}M".replace(".", ",")


def _wait(seconds) -> str:
    if seconds is None:
        return "—"
    if seconds < 60:
        return "<1 min"
    if seconds < 3600:
        return f"{round(seconds / 60)} min"
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours} h {minutes:02d} min"


def load_picks(season: str) -> list[dict]:
    picks = [
        p
        for p in fs.query(f"draft/{season}/picks")
        if p.get("status") == "applied" and p.get("global_pick")
    ]
    lines = {}
    response = requests.get(COMPETITION_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = (response.json().get("data")) or {}
    for player in (data.get("players") or {}).values():
        lines[int(player["id"])] = POSITION_CODE.get(player.get("position"), "?")
    for pick in picks:
        pick["line"] = lines.get(int(pick.get("player_id") or 0), "?")
    return sorted(picks, key=lambda p: p["global_pick"])


def render(picks: list[dict], season: str) -> str:
    total = len(picks)
    out = [f"# Draft {season} — disponibilidad\n"]
    out.append(
        f"{total} picks. Esto es lo que se agotó y cuándo: la referencia para "
        "decidir el año que viene en qué ronda hay que moverse por cada línea.\n"
    )

    out.append("\n## Cuándo se agotó cada línea\n")
    out.append("| Línea | Total | 1º | Último | Mitad | Precio medio |")
    out.append("|---|--:|--:|--:|--:|--:|")
    by_line = defaultdict(list)
    for pick in picks:
        by_line[pick["line"]].append(pick)
    for code, label in LINES:
        rows = by_line.get(code) or []
        if not rows:
            continue
        nums = [r["global_pick"] for r in rows]
        avg = sum(r.get("price") or 0 for r in rows) / len(rows)
        out.append(
            f"| **{label}** | {len(rows)} | {nums[0]} | {nums[-1]} "
            f"| {nums[len(nums) // 2]} | {_eur(avg)} |"
        )
    out.append(
        "\n«Mitad» es el pick en el que ya se había ido la mitad de la línea — "
        "el aviso de que quedan las sobras.\n"
    )

    out.append("\n## Ritmo por tramos de diez picks\n")
    buckets = sorted({(p["global_pick"] - 1) // 10 for p in picks})
    header = " | ".join(f"{b * 10 + 1}-{b * 10 + 10}" for b in buckets)
    out.append(f"| Línea | {header} |")
    out.append("|---" * (len(buckets) + 1) + "|")
    for code, label in LINES:
        counts = defaultdict(int)
        for pick in by_line.get(code) or []:
            counts[(pick["global_pick"] - 1) // 10] += 1
        cells = " | ".join(str(counts.get(b, 0) or "·") for b in buckets)
        out.append(f"| {label} | {cells} |")

    out.append("\n## Bandas de precio: cuál se vació antes\n")
    out.append("| Banda | Total | Último pick |")
    out.append("|---|--:|--:|")
    by_band = defaultdict(list)
    for pick in picks:
        by_band[_band(pick.get("price") or 0)].append(pick["global_pick"])
    for _, label in BANDS:
        nums = by_band.get(label)
        if nums:
            out.append(f"| {label} | {len(nums)} | {max(nums)} |")

    out.append("\n## Todos los picks\n")
    out.append("| # | Ronda | Manager | Jugador | Equipo | Línea | Precio | Espera |")
    out.append("|--:|--:|---|---|---|:-:|--:|--:|")
    for pick in picks:
        out.append(
            f"| {pick['global_pick']} | {pick.get('round', '—')} "
            f"| {pick.get('manager_name', '—')} | {pick.get('player_name', '—')} "
            f"| {pick.get('player_team', '—')} | {pick['line']} "
            f"| {_eur(pick.get('price'))} | {_wait(pick.get('waited_seconds'))} |"
        )
    return "\n".join(out) + "\n"


def write_history(picks: list[dict], path: str) -> None:
    """The same picks as `line,band,price,pick` — the model next year reads.

    The prose report is for the group chat; this is what `archetypes.py`
    consumes to answer "will he still be there at my pick?".
    """
    import csv

    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["pick", "line", "band", "price"])
        writer.writeheader()
        for pick in picks:
            writer.writerow(
                {
                    "pick": pick["global_pick"],
                    "line": pick["line"],
                    "band": _band(pick.get("price") or 0),
                    "price": pick.get("price") or 0,
                }
            )


def main() -> int:
    ap = argparse.ArgumentParser(description="Draft closing availability report")
    ap.add_argument("--season", default="26-27")
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--history-csv",
        default="",
        help="also write the machine-readable model archetypes.py reads",
    )
    args = ap.parse_args()
    # Both default into `history/`, one file per season: a draft's record is
    # the only artefact of this skill that outlives the week it was run.
    home = os.path.join(os.path.dirname(__file__), "..", "history")
    out = args.out or os.path.join(home, f"{args.season}.md")
    history_csv = args.history_csv or os.path.join(home, f"{args.season}.csv")
    os.makedirs(home, exist_ok=True)

    picks = load_picks(args.season)
    if not picks:
        print(f"No hay picks aplicados en draft/{args.season}/picks.")
        return 1
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(render(picks, args.season))
    print(f"{len(picks)} picks · escrito {out}")
    write_history(picks, history_csv)
    print(f"Modelo de disponibilidad · escrito {history_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
