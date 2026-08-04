"""Draft — Phase A: merge the closed-market CSV with live JP SofaScore.

Reads the Biwenger "primera-division" export (frozen prices for the chosen day)
and re-ranks every player by their current Jornada Perfecta SofaScore, adding a
value-per-million column and flagging players with no JP data.

Prices are frozen (the CSV); JP scores are fetched live via
`core.sdk.jp.fetch_all_players` — which self-invalidates on JP's own
`updated_at`, so re-running days later picks up fresh scores with the same
prices, no flags needed.

Reuses the production matcher (`player_matching.find_player_match`) so the
Biwenger↔JP name overrides (Vinícius Jr → Vini Jr, …) come for free.

Run from the repo root with the JP token available (api `.env` or JP_AUTH_TOKEN):

    PYTHONPATH=. python3 .claude/skills/draft/scripts/draft_ranking.py \
        --csv /path/to/primera-division.csv --out draft-ranked.csv
"""

import argparse
import csv
import statistics
from collections import Counter
import os
import sys

from core.sdk.jp import fetch_all_players, get_predict_rate
from packages.biwenger_tools.api.logic.player_matching import (
    build_jp_index,
    find_player_match,
)
from packages.biwenger_tools.api.player_formatting import SCORE_SF

# Biwenger export uses full Spanish position words; map to the reglamento's
# line codes so Phase B can reason about squad composition.
_POSITION = {
    "Portero": "PT",
    "Defensa": "DF",
    "Centrocampista": "MC",
    "Delantero": "DL",
}


_API_ENV = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "..",
    "packages",
    "biwenger_tools",
    "api",
    ".env",
)


def _jp_token() -> str:
    """JP auth token, resolved the way production does (the real token lives in
    `BIWENGER_CREDENTIALS_JSON.jp_auth_token`). Loads the api `.env` explicitly
    by path so the script works from any CWD, not just the api dir."""
    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.abspath(_API_ENV))
    except Exception:
        pass
    try:
        from packages.biwenger_tools.api import config

        token = config.JP_AUTH_TOKEN
    except Exception:
        token = ""
    return token or os.getenv("JP_AUTH_TOKEN", "")


def _read_market_csv(path: str) -> list[dict]:
    """Rows from the Biwenger export (utf-8-sig, ';'). Keeps name, team,
    position (mapped) and the frozen price as an int."""
    with open(path, encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        rows = []
        for r in reader:
            name = (r.get("Jugador") or "").strip()
            if not name:
                continue
            try:
                price = int(r.get("Precio") or 0)
            except ValueError:
                price = 0
            pos = (r.get("Posición") or "").strip()
            rows.append(
                {
                    "name": name,
                    "team": (r.get("Equipo") or "").strip(),
                    "position": _POSITION.get(pos, pos),
                    "price": price,
                }
            )
    return rows


def rank(
    csv_path: str, jp_players: list[dict], score_type: int = SCORE_SF
) -> list[dict]:
    """Attach live JP SofaScore + value/M to each market row, ranked SF desc.
    Unmatched players (no JP data) sort last, flagged."""
    jp_index = build_jp_index(jp_players)
    out = []
    for row in _read_market_csv(csv_path):
        jp = find_player_match(row["name"], jp_index)
        sf = get_predict_rate(jp, score_type) if jp else None
        price_m = row["price"] / 1_000_000 if row["price"] else None
        value = round(sf / price_m, 1) if (sf and price_m) else None
        out.append(
            {
                **row,
                "sofascore": sf,
                "value_per_m": value,
                "no_jp_data": sf is None,
            }
        )
    # JP hands one flat score to players it cannot rate (promoted clubs, fresh
    # signings). It is a top-decile number on 1.5M players, so it reads as real
    # data in the CSV unless it is flagged here too — the archetype generator
    # drops them, but anyone reading this file directly would be misled.
    scores = [r["sofascore"] for r in out if r["sofascore"] is not None]
    placeholder = _detect_placeholder(scores)
    for r in out:
        r["jp_placeholder"] = placeholder is not None and r["sofascore"] == placeholder

    # SF desc; unmatched (None) last, then by price desc as a stable tiebreak.
    out.sort(
        key=lambda r: (r["sofascore"] is not None, r["sofascore"] or 0), reverse=True
    )
    return out


def _detect_placeholder(scores: list[int]) -> int | None:
    """The one flat score JP repeats for unrated players, or None.

    Same detection the archetype generator uses: a spike on one exact value
    well above the median.
    """
    if not scores:
        return None
    counts = Counter(scores)
    med = statistics.median(scores)
    # Only values above the median can be the placeholder, and they must be
    # ranked among themselves: scanning the overall most-common first lets a
    # crowd of zero-minute players bury the spike.
    above = Counter({v: n for v, n in counts.items() if v > med})
    for value, n in above.most_common(8):
        if n < 5:
            continue
        window = [counts.get(v, 0) for v in range(value - 15, value + 16) if v != value]
        if window and n > 4 * (sum(window) / len(window)):
            return value
    return None


def write_csv(rows: list[dict], path: str) -> None:
    cols = [
        "name",
        "team",
        "position",
        "price",
        "sofascore",
        "value_per_m",
        "no_jp_data",
        "jp_placeholder",
    ]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c) for c in cols})


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Draft Phase A — rank market by JP SofaScore"
    )
    ap.add_argument("--csv", required=True, help="Biwenger closed-market export")
    ap.add_argument("--out", default="draft-ranked.csv", help="ranked output CSV")
    args = ap.parse_args()

    token = _jp_token()
    if not token:
        print("No JP auth token (api .env JP_AUTH_TOKEN empty).", file=sys.stderr)
        return 1

    try:
        from packages.biwenger_tools.api import config

        competition = config.JP_COMPETITION
        score_type = config.JP_SCORE_TYPE
    except Exception:
        competition, score_type = 1, SCORE_SF

    jp_players = fetch_all_players(
        token, competition=competition, score_type=score_type
    )
    if not jp_players:
        print(
            f"JP returned 0 players (competition={competition}). The token is "
            "likely a placeholder — the real jp_auth_token is a production "
            "secret, not in the dev .env.",
            file=sys.stderr,
        )
        return 2
    rows = rank(args.csv, jp_players, score_type)
    write_csv(rows, args.out)

    matched = [r for r in rows if not r["no_jp_data"]]
    missing = [r for r in rows if r["no_jp_data"]]
    print(
        f"Players: {len(rows)} | matched JP: {len(matched)} "
        f"| no JP data: {len(missing)}"
    )
    print(f"Wrote {args.out}")
    print("\nTop 10 by SofaScore:")
    for r in rows[:10]:
        sf = r["sofascore"] if r["sofascore"] is not None else "--"
        print(
            f"  {str(sf):>4}  {r['name']:<22} {r['position']:<3} "
            f"{r['price'] / 1e6:>6.2f}M  v/M {r['value_per_m']}"
        )
    if missing:
        preview = ", ".join(r["name"] for r in missing[:15])
        tail = " …" if len(missing) > 15 else ""
        print(f"\nNo JP data ({len(missing)}): {preview}{tail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
