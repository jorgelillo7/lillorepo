"""Grade the Oráculo blend against Jornada Perfecta alone, or seed the real
outcome of rounds the ledger never captured a projection for.

    R=packages/biwenger_tools/scripts/projections/report.py

    PYTHONPATH=. python3 $R                      # grade, dry run
    PYTHONPATH=. python3 $R --apply              # grade and cache the outcome
    PYTHONPATH=. python3 $R --backfill           # seed older rounds, dry run
    PYTHONPATH=. python3 $R --backfill --apply   # seed them for real

**How to read the output: `docs/technical/backend/projection-ledger.md`.**
The numbers are easy to produce and easy to misread, and every way of
misreading them ends in changing a dial for no reason.

Two independent modes, one script:

- Default (grading): for every stored round Biwenger reports as finished,
  score the blended eleven and the Jornada-Perfecta-alone eleven from real
  per-match points, and print the pair side by side. `--apply` additionally
  caches the real outcome back into Firestore
  (`projection_ledger_store.write_actual`) so a second run never re-fetches
  it — the outcome of a finished round never changes.
- `--backfill`: for finished rounds with no stored projection at all, seed
  the real outcome anyway — `has_projection: False`. There is nothing to
  grade there; the value is exercising this read path and seeding the half
  of the comparison that does exist. `--apply` writes; without it, dry-run.

Per-player real points come from Biwenger's public player-detail endpoint,
read sequentially with a delay and cached on disk — the same rate limit
`fetch_real_points.py` documents: roughly 500 requests per 8h window, shared
with the phone app.

ADC (`gcloud auth application-default login`) for Firestore. Biwenger
credentials from `.env`, like every other script here.
"""

import argparse
import json
import os
import time
from datetime import datetime

import requests

from core.constants import MADRID_TZ
from core.sdk.biwenger import BIWENGER_CF_BASE
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import projection_ledger, projection_ledger_store
from packages.biwenger_tools.api.logic.orchestration import build_biwenger_session
from packages.biwenger_tools.api.logic import real_points as real_points_mod
from packages.biwenger_tools.api.logic.real_points import (
    personalizado,
    reports_for_round,
)

PLAYER_URL = (
    BIWENGER_CF_BASE
    + "/players/la-liga/{slug}?fields=*,reports(*,match(*,round(*)),rawStats(*))"
)
HEADERS = {"User-Agent": "Mozilla/5.0"}


class _PlayerFetcher:
    """Sequential, cached, rate-limit-aware reader of the public player
    endpoint. Mirrors the draft skill's `fetch_real_points.py::Fetcher`."""

    def __init__(self, cache_dir: str, delay: float, max_requests: int):
        self.cache_dir = cache_dir
        self.delay = delay
        self.remaining = max_requests
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


def _slug_index(biwenger) -> dict:
    players = biwenger.get_all_players_data_map(config.ALL_PLAYERS_DATA_URL)
    return {bw_id: p.get("slug") for bw_id, p in players.items() if p.get("slug")}


def _real_points_for(
    fetcher: _PlayerFetcher, slug_by_id: dict, player_ids, round_id: int
) -> dict:
    """`({bw_id: points}, {bw_id: reports counted})` for exactly the players
    named and exactly the round asked for — never the season, never the
    market. The second map is what tells a real zero from an empty read."""
    points, counted = {}, {}
    for player_id in sorted(set(player_ids)):
        slug = slug_by_id.get(player_id)
        if not slug:
            continue
        player = fetcher.player(slug)
        if player is None:
            continue
        matches = reports_for_round(player.get("reports") or [], round_id)
        points[player_id] = personalizado(matches, player.get("position"))["points"]
        counted[player_id] = len(matches)
    return points, counted


def _fetch_actual_for_projection(biwenger, fetcher, slug_by_id, doc: dict) -> dict:
    round_league = biwenger.get_round_league(doc["round_id"])
    applied = projection_ledger.extract_applied_lineup(round_league, biwenger.user_id)

    blended = doc.get("blended_xi") or {}
    jp_only = doc.get("jp_only_xi") or {}
    ids = set(blended.get("player_ids") or []) | set(jp_only.get("player_ids") or [])
    real_points, _ = _real_points_for(fetcher, slug_by_id, ids, doc["round_id"])

    return {
        "fetched_at": datetime.now(MADRID_TZ).isoformat(),
        "applied": applied,
        "player_points": real_points,
        "blended_total": projection_ledger.xi_real_points(
            blended.get("player_ids") or [], blended.get("captain_id"), real_points
        ),
        "jp_only_total": projection_ledger.xi_real_points(
            jp_only.get("player_ids") or [], jp_only.get("captain_id"), real_points
        ),
    }


def _print_comparison(doc: dict, actual: dict) -> None:
    blended = doc.get("blended_xi") or {}
    jp_only = doc.get("jp_only_xi") or {}
    name_by_id = {p["bw_id"]: p["name"] for p in doc.get("players") or []}
    points = actual["player_points"]

    print(f"\n=== {doc.get('round_name') or doc['round_id']} ({doc['season']}) ===")
    print(
        f"  Blend  {blended.get('formation') or '?'}  real: {actual['blended_total']}"
    )
    print(
        f"  JP     {jp_only.get('formation') or '?'}  real: {actual['jp_only_total']}"
    )
    delta = actual["blended_total"] - actual["jp_only_total"]
    print(f"  Diferencia (blend - JP): {delta:+d}")

    if not doc.get("xi_differs"):
        print("  (mismo once — nada que aprender esta jornada)")
        return
    diff = doc.get("xi_diff") or {}
    for player_id in diff.get("only_blended") or []:
        name = name_by_id.get(player_id, player_id)
        print(f"  + solo el blend fichó a {name}: {points.get(player_id, '¿?')} pts")
    for player_id in diff.get("only_jp") or []:
        name = name_by_id.get(player_id, player_id)
        print(f"  + solo JP fichó a {name}: {points.get(player_id, '¿?')} pts")


def _print_verdict(graded: list) -> None:
    """Print what `projection_ledger.grade` concluded, and nothing more.

    The rule for what counts as evidence and how much is enough lives there,
    under test. A threshold invented in a reporting script is one nobody ever
    checks, and this script exists precisely to stop numbers being trusted
    because they were printed.
    """
    merged = [{**doc, "actual": actual} for doc, actual in graded]
    summary = projection_ledger.grade(merged)
    print(
        f"\n{summary['rounds_stored']} jornadas evaluadas, "
        f"{summary['rounds_compared']} con onces distintos."
    )
    if summary["verdict"] is None:
        print(
            f"Faltan {summary['rounds_needed']} jornadas con onces distintos "
            "para poder concluir nada. Por debajo de ese umbral, una racha de "
            "suerte y un efecto real son indistinguibles."
        )
        print("No cambies ningún dial con esto: para eso está el umbral.")
        return
    average = summary["total_delta"] / summary["rounds_compared"]
    print(
        f"El blend ganó {summary['blend_won']}/{summary['rounds_compared']} "
        f"jornadas donde discrepó con JP; diferencia media {average:+.1f} "
        "pts/jornada."
    )
    print("Sigue siendo una dirección, no una prueba. Antes de actuar, lee")
    print("  docs/technical/backend/projection-ledger.md")


def _run_grading(biwenger, fetcher: _PlayerFetcher, apply: bool) -> int:
    docs = [
        doc for doc in projection_ledger_store.list_all() if doc.get("has_projection")
    ]
    if not docs:
        print("No hay proyecciones guardadas todavía.")
        return 0

    slug_by_id = _slug_index(biwenger)
    graded = []
    for doc in sorted(docs, key=lambda d: d.get("round_id") or 0):
        round_id = doc["round_id"]
        if (biwenger.get_round(round_id).get("status") or "") != "finished":
            print(
                f"Jornada {doc.get('round_name') or round_id}: "
                "aún no terminada — se omite."
            )
            continue

        actual = doc.get("actual")
        if actual is None:
            actual = _fetch_actual_for_projection(biwenger, fetcher, slug_by_id, doc)
            if apply:
                projection_ledger_store.write_actual(doc["season"], round_id, actual)

        _print_comparison(doc, actual)
        graded.append((doc, actual))

    _print_verdict(graded)
    if not apply and any(doc.get("actual") is None for doc in docs):
        print("\nEnsayo — el resultado real no se ha guardado. Repite con --apply.")
    return 0


def _run_backfill(biwenger, fetcher: _PlayerFetcher, apply: bool) -> int:
    season = config.CURRENT_SEASON
    current_round = biwenger.get_round()
    already_stored = {doc.get("round_id") for doc in projection_ledger_store.list_all()}
    finished_ids = [
        r["id"]
        for r in ((current_round.get("season") or {}).get("rounds") or [])
        if r.get("status") == "finished" and r.get("id") not in already_stored
    ]
    if not finished_ids:
        print("Nada que rellenar: cada jornada terminada ya tiene un registro.")
        return 0

    slug_by_id = _slug_index(biwenger)
    for round_id in finished_ids:
        round_league = biwenger.get_round_league(round_id)
        applied = projection_ledger.extract_applied_lineup(
            round_league, biwenger.user_id
        )
        if applied is None:
            print(
                f"Jornada {round_id}: no encuentro tu alineación aplicada — se omite."
            )
            continue

        real_points, counted = _real_points_for(
            fetcher, slug_by_id, applied["player_ids"], round_id
        )
        missing = real_points_mod.missing_reports(
            applied["player_ids"], real_points, counted
        )
        if missing:
            print(
                f"Jornada {round_id}: {len(missing)} de "
                f"{len(applied['player_ids'])} alineados sin informe — "
                "no es un cero, es que no hay dato. Se omite."
            )
            continue
        applied_total = projection_ledger.xi_real_points(
            applied["player_ids"], applied["captain_id"], real_points
        )
        actual = {
            "fetched_at": datetime.now(MADRID_TZ).isoformat(),
            "applied": applied,
            "player_points": real_points,
            "applied_total": applied_total,
        }
        round_name = biwenger.get_round(round_id).get("name")
        print(
            f"Jornada {round_name or round_id}: "
            f"{applied['formation']}, {applied_total} pts reales."
        )
        if apply:
            projection_ledger_store.write_backfill(
                season, round_id, round_name, actual["fetched_at"], actual
            )

    if not apply:
        print(
            f"\nEnsayo — {len(finished_ids)} jornadas se rellenarían. "
            "Repite con --apply."
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--backfill",
        action="store_true",
        help="seed real outcomes for finished rounds with no stored projection",
    )
    ap.add_argument(
        "--apply", action="store_true", help="write to Firestore (default: dry run)"
    )
    ap.add_argument(
        "--delay", type=float, default=1.0, help="seconds between player fetches"
    )
    ap.add_argument(
        "--max-requests",
        type=int,
        default=60,
        help="hard cap on live player-detail requests this run makes",
    )
    ap.add_argument(
        "--cache-dir",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)), ".cache", "players"
        ),
    )
    args = ap.parse_args()

    biwenger = build_biwenger_session()
    fetcher = _PlayerFetcher(args.cache_dir, args.delay, args.max_requests)

    if args.backfill:
        return _run_backfill(biwenger, fetcher, apply=args.apply)
    return _run_grading(biwenger, fetcher, apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
