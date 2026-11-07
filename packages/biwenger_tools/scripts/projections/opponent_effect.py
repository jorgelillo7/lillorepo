"""Does a fixture against Barcelona or Real Madrid sink a player's points, and
does Jornada Perfecta's projection already account for it?

    PYTHONPATH=. python3 packages/biwenger_tools/scripts/projections/opponent_effect.py

Read-only: it writes nothing, so there is no `--apply`.

**How to read the output: `docs/technical/backend/projection-ledger.md`,
"The opponent effect".** Each appearance is compared with the same player's
own mean in his other games, so a weak defender is never mistaken for a bad
fixture.

Points are SofaScore (`score=2`), the base Jornada Perfecta projects, read
from Biwenger's public round endpoint: one request per finished round, on the
`cf` host, not the account's player-detail budget. The league's own scoring
adds play, win and clean-sheet bonuses on top, which only widen a gap against
a side that wins and scores.

The second half needs `league_jp` in the projection ledger, captured every
morning from round 13 on: ADC (`gcloud auth application-default login`) for
Firestore.
"""

import argparse
import time

import requests

from core.sdk.biwenger import BIWENGER_CF_BASE
from packages.biwenger_tools.api.logic import opponent_effect as oe
from packages.biwenger_tools.api.logic import projection_ledger_store
from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID

ROUND_URL = BIWENGER_CF_BASE + "/rounds/la-liga"
HEADERS = {"User-Agent": "Mozilla/5.0"}
SOFASCORE = 2

GROUPS = (
    ("DEF+POR", {GK, DEF}),
    ("DEF", {DEF}),
    ("POR", {GK}),
    ("MED", {MID}),
    ("DEL", {FWD}),
)


def _get_round(round_id: int | None) -> dict:
    url = ROUND_URL if round_id is None else f"{ROUND_URL}/{round_id}"
    response = requests.get(
        url,
        params={"lang": "es", "score": SOFASCORE},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data") or {}


def _finished_rounds(delay: float) -> list[dict]:
    season = (_get_round(None).get("season") or {}).get("rounds") or []
    ids = [r["id"] for r in season if r.get("status") == "finished"]
    rounds = []
    for round_id in ids:
        rounds.append(_get_round(round_id))
        time.sleep(delay)
    return rounds


def _line(label: str, summary: dict | None) -> str:
    if summary is None:
        return f"  {label:16s} n=0"
    return (
        f"  {label:16s} n={summary['n']:3d}  media {summary['mean']:+5.2f}  "
        f"mediana {summary['median']:+5.2f}  "
        f"por debajo de su media {summary['below']}/{summary['n']}"
    )


def _print_effect(apps: list, opponents: list[str]) -> None:
    print("Puntos frente a la media propia en el resto de partidos (SofaScore)")
    for label, positions in GROUPS:
        ranked = sorted(
            (
                (oe.summarize(oe.opponent_deltas(apps, opp, positions)), opp)
                for opp in opponents
            ),
            key=lambda pair: pair[0]["mean"] if pair[0] else 0,
        )
        print(f"\n{label} — los tres rivales peores y los vigilados")
        shown = [opp for _, opp in ranked[:3]] + list(oe.WATCHED)
        for summary, opp in ranked:
            if opp in shown:
                print(_line(opp, summary))


def _print_matches(apps: list) -> None:
    for opp in oe.WATCHED:
        matches = oe.by_match(oe.opponent_deltas(apps, opp, {GK, DEF}))
        below = sum(1 for m in matches if m["mean"] < 0)
        print(f"\nDEF+POR contra {opp}, por partido: {below}/{len(matches)} negativos")
        for m in matches:
            where = "casa" if m["home"] else "fuera"
            print(
                f"  {m['round_name']:24s} {m['team']:16s} {where:5s} "
                f"media {m['mean']:+5.1f}  (n={m['n']})"
            )


def _print_jp(apps: list) -> None:
    league_jp = {
        doc["round_id"]: doc["league_jp"]
        for doc in projection_ledger_store.list_all()
        if doc.get("league_jp")
    }
    print(
        f"\nJornada Perfecta frente a lo real ({len(league_jp)} jornadas con league_jp)"
    )
    for opp in oe.WATCHED:
        rows = oe.jp_vs_real(apps, league_jp, opp, {GK, DEF})
        if not rows:
            print(f"  {opp}: sin muestras todavía")
            continue
        jp = oe.summarize([(j, None) for j, _, _ in rows])
        real = oe.summarize([(r, None) for _, r, _ in rows])
        print(
            f"  {opp}: n={len(rows)}  JP {jp['mean']:+6.1f} SF frente a su media  ·  "
            f"real {real['mean']:+5.2f} pts frente a su media"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument(
        "--no-ledger", action="store_true", help="skip the Firestore half"
    )
    args = parser.parse_args()

    apps = oe.appearances(_finished_rounds(args.delay))
    opponents = sorted({a.opponent for a in apps})
    print(f"{len(apps)} actuaciones, {len({a.game_id for a in apps})} partidos\n")
    _print_effect(apps, opponents)
    _print_matches(apps)
    if not args.no_ledger:
        _print_jp(apps)


if __name__ == "__main__":
    main()
