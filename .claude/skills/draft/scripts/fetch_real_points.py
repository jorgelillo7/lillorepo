"""Draft — Phase 2: real "Personalizado" points and games played, for a shortlist.

The league scores `Personalizado` (scoreID 100), which Biwenger never serves as a
total: it is computed client-side from per-match `rawStats`. This walks a
**shortlist** of players, not the market, and writes `name,points,games,...` for
the archetype generator to consume.

Bounded on purpose. Biwenger allows ~500 requests per 8-hour window **per
account**, shared with the app: a parallel sweep of the market locks the whole
league out of Biwenger for hours. Hence sequential, delayed, capped by
`--max-requests`, cached on disk, and it stops at the first 429.

    PYTHONPATH=. python3 .claude/skills/draft/scripts/fetch_real_points.py \
        --shortlist draft-shortlist.csv --out draft-real-points.csv
"""

import argparse
import csv
import json
import os
import sys
import time
import unicodedata

import requests

CF_BASE = "https://cf.biwenger.com/api/v2"
COMPETITION_URL = f"{CF_BASE}/competitions/la-liga/data?lang=es&score=2"
PLAYER_URL = CF_BASE + "/players/la-liga/{slug}?fields=*,reports(*),seasons(*)"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Biwenger position ids.
GK, DEF = 1, 2
POSITION_CODE = {1: "PT", 2: "DF", 3: "MC", 4: "DL"}
SOFASCORE_SEASON_KEY = "2"


def _norm(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFD", (text or "").lower())
        if unicodedata.category(c) != "Mn"
    ).strip()


def personalizado(reports: list, position: int) -> dict:
    """This league's custom total from per-match `rawStats`.

    Verified to the point against two controls of different lines: Vinícius
    Jr 330 (forward, 296 SofaScore base) and Joan García 274 (goalkeeper, 190).

    Biwenger's `star` flag is deliberately ignored — including it as the
    config's MVP bonus overshoots both controls (345 and 277).
    """
    total = base = games = minutes = wins = clean = 0
    for report in reports:
        stats = report.get("rawStats") or {}
        played = stats.get("minutesPlayed") or 0
        if not played:
            continue
        games += 1
        minutes += played
        score = stats.get("score2") or 0
        base += score
        points = score
        # Being on the pitch is worth points by itself, and again if the team
        # wins — the single biggest reason a starter beats a better substitute.
        if played > 65:
            points += 1
            if stats.get("win"):
                points += 1
                wins += 1
            if stats.get("lost"):
                points -= 1
        if stats.get("cleanSheet"):
            clean += 1
            points += 2 if position == GK else (1 if position == DEF else 0)
        points -= stats.get("yellowCard") or 0
        points -= stats.get("goalsPenalty") or 0  # a penalty goal scores less
        points -= 2 * (stats.get("penaltyMissed") or 0)
        if position == GK:
            points += (stats.get("goals") or 0) + 2 * (stats.get("assists") or 0)
        elif position == DEF:
            points += stats.get("assists") or 0
        total += points
    return {
        "points": total,
        "sofascore_real": base,
        "games": games,
        "minutes": minutes,
        "wins": wins,
        "clean_sheets": clean,
    }


def _season_row(seasons: list, season_slug: str) -> dict:
    for season in seasons or []:
        if season.get("slug") == season_slug:
            return season
    return {}


class Fetcher:
    """Sequential, cached, rate-limit-aware reader of the public player endpoint."""

    def __init__(self, cache_dir: str, delay: float, max_requests: int):
        self.cache_dir = cache_dir
        self.delay = delay
        self.remaining = max_requests
        self.requests_made = 0
        self.rate_limited = False
        os.makedirs(cache_dir, exist_ok=True)

    def player(self, slug: str) -> dict | None:
        cached = os.path.join(self.cache_dir, f"{slug}.json")
        if os.path.exists(cached):
            with open(cached, encoding="utf-8") as fh:
                return json.load(fh)
        if self.rate_limited or self.remaining <= 0:
            return None
        self.remaining -= 1
        self.requests_made += 1
        response = requests.get(
            PLAYER_URL.format(slug=slug), headers=HEADERS, timeout=25
        )
        # 429 means the window is spent for every consumer of this account,
        # the phone app included. Stop; do not retry into a deeper hole.
        if response.status_code == 429:
            self.rate_limited = True
            return None
        response.raise_for_status()
        data = response.json().get("data") or {}
        with open(cached, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        time.sleep(self.delay)
        return data


def _read_shortlist(path: str) -> list[str]:
    with open(path, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    for key in ("name", "Jugador", "jugador", "player"):
        if rows and key in rows[0]:
            return [r[key].strip() for r in rows if r.get(key, "").strip()]
    raise SystemExit(f"{path}: no 'name' column found")


def build_index(players: dict) -> dict:
    index = {}
    for player in players.values():
        index.setdefault(_norm(player.get("name")), player)
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description="Draft Phase 2 — real custom points")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--shortlist", help="CSV with a 'name' column")
    src.add_argument("--names", help="comma-separated player names")
    ap.add_argument("--out", default="draft-real-points.csv")
    ap.add_argument("--season", default="2025-2026", help="season slug to report")
    ap.add_argument(
        "--max-requests",
        type=int,
        default=45,
        help="hard cap on live requests (500 per 8h window, shared with the app)",
    )
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between calls")
    ap.add_argument(
        "--cache-dir",
        default=os.path.join(os.path.dirname(__file__), "..", ".cache", "players"),
    )
    args = ap.parse_args()

    names = (
        _read_shortlist(args.shortlist)
        if args.shortlist
        else [n.strip() for n in args.names.split(",") if n.strip()]
    )
    if len(names) > args.max_requests:
        print(
            f"Shortlist has {len(names)} players but the cap is "
            f"{args.max_requests}. Narrow the shortlist or raise --max-requests "
            "deliberately — this budget is shared with the phone app.",
            file=sys.stderr,
        )
        return 1

    competition = requests.get(COMPETITION_URL, headers=HEADERS, timeout=30).json()
    data = competition.get("data") or {}
    teams = {int(k): v["name"] for k, v in (data.get("teams") or {}).items()}
    index = build_index(data.get("players") or {})

    fetcher = Fetcher(args.cache_dir, args.delay, args.max_requests)
    rows, unmatched, no_history = [], [], []
    for name in names:
        entry = index.get(_norm(name))
        if not entry:
            unmatched.append(name)
            continue
        player = fetcher.player(entry["slug"])
        if player is None:
            unmatched.append(f"{name} (sin datos: límite alcanzado)")
            continue
        position = player.get("position") or entry.get("position")
        reports = [
            r
            for r in (player.get("reports") or [])
            if ((r.get("match") or {}).get("competition") or {}).get("slug")
            == "la-liga"
        ]
        computed = personalizado(reports, position)
        season = _season_row(player.get("seasons"), args.season)
        season_points = season.get("points") or {}
        # No La Liga minutes means no history here, whatever `seasons` says:
        # that block counts every competition, so a player arriving from Ligue 1
        # or from Segunda would otherwise be published as a genuine zero — a
        # worse lie than an empty cell, because the optimiser would believe it.
        if not computed["games"]:
            no_history.append(f"{name} ({season.get('games') or 0} partidos fuera)")
            continue
        rows.append(
            {
                "name": name,
                "biwenger_name": player.get("name"),
                "team": teams.get(entry.get("teamID"), "?"),
                "position": POSITION_CODE.get(position, position),
                "price": entry.get("price") or 0,
                "points": computed["points"],
                "games": computed["games"],
                "season_games": season.get("games") or computed["games"],
                "minutes": computed["minutes"],
                "sofascore_real": (
                    season_points.get(SOFASCORE_SEASON_KEY)
                    or computed["sofascore_real"]
                ),
                "wins": computed["wins"],
                "clean_sheets": computed["clean_sheets"],
            }
        )
        if fetcher.rate_limited:
            print(
                "429 de Biwenger — ventana agotada. Paro aquí para no dejar "
                "la app sin servicio; lo descargado queda en caché.",
                file=sys.stderr,
            )
            break

    for row in rows:
        games = row["games"] or 0
        row["per_game"] = round(row["points"] / games, 2) if games else None
        price_m = (row["price"] or 0) / 1_000_000
        row["per_m"] = round(row["points"] / price_m, 1) if price_m else None

    cols = [
        "name",
        "team",
        "position",
        "price",
        "points",
        "games",
        "per_game",
        "per_m",
        "minutes",
        "season_games",
        "sofascore_real",
        "wins",
        "clean_sheets",
        "biwenger_name",
    ]
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: r["points"], reverse=True):
            writer.writerow({c: row.get(c) for c in cols})

    print(f"{len(rows)} jugadores · {fetcher.requests_made} peticiones live")
    print(f"Escrito {args.out}")
    print(
        f"\n{'Jugador':<22}{'Eq':<14}{'Pos':<5}{'Pts':>5}{'PJ':>4}{'/PJ':>7}{'/M':>7}"
    )
    for row in sorted(rows, key=lambda r: r["points"], reverse=True):
        print(
            f"{row['name'][:21]:<22}{row['team'][:13]:<14}{row['position']:<5}"
            f"{row['points']:>5}{row['games']:>4}{row['per_game'] or 0:>7.2f}"
            f"{row['per_m'] or 0:>7.1f}"
        )
    if no_history:
        print(
            f"\nSin minutos en Primera ({len(no_history)}) — quedan fuera del "
            f"CSV, no valen 0: {', '.join(no_history)}"
        )
    if unmatched:
        print(f"\nSin emparejar ({len(unmatched)}): {', '.join(unmatched)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
