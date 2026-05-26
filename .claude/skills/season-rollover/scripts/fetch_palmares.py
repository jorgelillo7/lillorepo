"""Fetch end-of-season palmares data and write the palmarés record.

Combines three Biwenger endpoints for the current season:

  * standings        — final position, team name, total points
  * report/rounds    — jornadas ganadas + posición media (per user)
  * report/roundPoints — total points, mejor jornada, peor jornada (per user)

Resolves real names by user_id via ``core.constants.LEAGUE_MEMBERS``. Emits:

  * A pretty-printed Firestore document preview (the doc the web reads from)
  * A per-user summary table for terminal review
  * Optionally writes the doc to Firestore at ``palmares/<season>``

Usage::

    python fetch_palmares.py <season> \\
        [--abandoned-user "<real_name>=<reason>"]... \\
        [--write-firestore]

Required env (Biwenger): BIWENGER_EMAIL, BIWENGER_PASSWORD.
``LEAGUE_ID`` defaults to ``core.constants.LEAGUE_ID``.
Required env (--write-firestore): GOOGLE_CLOUD_PROJECT (e.g. biwenger-tools).

The --abandoned-user flag injects a row at the bottom of the standings table
for accounts deleted mid-season (the user_id is no longer in Biwenger). Use
it once per abandoned member with the shape ``NAME=TEAM=REASON``, e.g.
``--abandoned-user "Alberto=#NOALOSCLAUSULAZOS=abandono"``. Leave the team
slot empty if unknown: ``"Someone==abandono"``.
"""

import argparse
import json
import os
import sys

# Allow running from repo root without installing packages.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../"))

from core.constants import LEAGUE_ID as DEFAULT_LEAGUE_ID  # noqa: E402
from core.constants import LEAGUE_MEMBERS  # noqa: E402
from core.domain.models import Palmares, SeasonStanding  # noqa: E402
from core.sdk.biwenger import (  # noqa: E402
    ACCOUNT_URL,
    LOGIN_URL,
    BiwengerClient,
    clausulazos_url,
    league_round_points_report_url,
    league_round_report_url,
    league_standings_url,
)


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_standings_table(
    standings: list,
    rounds_rows: list,
    points_rows: list,
) -> list[SeasonStanding]:
    """Cross-reference the three endpoints by user_id."""
    by_user_rounds = {r.get("Usuario", {}).get("id"): r for r in rounds_rows}
    by_user_points = {r.get("Usuario", {}).get("id"): r for r in points_rows}

    table: list[SeasonStanding] = []
    for entry in standings:
        uid = entry.get("id")
        if not uid:
            continue
        rounds = by_user_rounds.get(uid, {})
        points = by_user_points.get(uid, {})
        table.append(
            SeasonStanding(
                position=_to_int(entry.get("position")),
                user_id=int(uid),
                team_name=entry.get("name", ""),
                real_name=LEAGUE_MEMBERS.get(int(uid), ""),
                points=_to_int(entry.get("points") or points.get("Puntos")),
                best_round=_to_int(points.get("Mejor jornada")),
                worst_round=_to_int(points.get("Peor jornada")),
                rounds_won=_to_int(rounds.get("Jornadas ganadas")),
                avg_position=_to_float(rounds.get("Posición media")),
            )
        )
    return table


def _append_abandoned(
    table: list[SeasonStanding],
    abandoned: list[tuple[str, str, str]],
) -> None:
    """Append rows for accounts deleted mid-season.

    Abandoned rows go after the real standings, so they end up in the last
    positions and inherit the farolillo — league rule: ``el que se levanta
    de la mesa pierde``.
    """
    next_position = max((s.position for s in table), default=0) + 1
    for real_name, team_name, reason in abandoned:
        table.append(
            SeasonStanding(
                position=next_position,
                user_id=0,
                team_name=team_name or "—",
                real_name=real_name,
                note=reason,
            )
        )
        next_position += 1


def _compute_aggregates(table: list[SeasonStanding]) -> dict:
    """Aggregate fields rendered in the right-hand 'Datos de la Temporada' block."""
    active = [s for s in table if s.user_id]
    if not active:
        return {"record_puntos": "", "jornadas_ganadas": ""}

    record_holder = max(active, key=lambda s: s.best_round)
    rounds_winner = max(active, key=lambda s: s.rounds_won)

    record_label = (record_holder.real_name or record_holder.team_name or "").lower()
    winner_label = (rounds_winner.real_name or rounds_winner.team_name or "").lower()
    record_puntos = (
        f"{record_holder.best_round} @{record_label}"
        if record_holder.best_round and record_label
        else ""
    )
    jornadas_ganadas = (
        f"{rounds_winner.rounds_won} @{winner_label}"
        if rounds_winner.rounds_won and winner_label
        else ""
    )
    return {
        "record_puntos": record_puntos,
        "jornadas_ganadas": jornadas_ganadas,
    }


def _build_palmares(
    season: str,
    table: list[SeasonStanding],
    clausulazos_total: int,
) -> Palmares:
    """Roll the table into the Palmares document the web reads.

    League payout rule (Mochileros):
      - Half win — invited to lunch by the losers.
      - Half lose — pay their own + pay for the winners.
      - With an odd number of players, the single middle position is
        neutral and pays only its own.

    Concretely (``N`` = number of finishers including abandoned rows):
      - ``losers_count = N // 2``
      - ``neutros_count = N % 2`` (0 if even, 1 if odd)
      - ``winners_count = N - losers_count - neutros_count``

    Examples — N=6 → 3+0+3; N=7 → 3+1+3; N=8 → 4+0+4.

    Mapping to the Palmares fields:
      - ``campeon`` / ``subcampeon`` / ``tercero`` → positions 1, 2, 3
        (podium medals; extra winners beyond 3rd don't get a labelled slot).
      - ``multas`` → every losing position, in ascending order. The last
        entry of this list is the farolillo (cosmetic distinction only,
        rendered with the 🔴 icon at template level). League rule applies:
        an abandoned account ends up last and inherits the farolillo.
      - ``neutros`` → the single neutral position when N is odd; empty
        when N is even.

    Records (``record_puntos`` / ``jornadas_ganadas``) only consider active
    users — abandoned rows have zeros for both, so they never claim them.
    """
    sorted_table = sorted(table, key=lambda s: s.position)
    by_position = {s.position: s for s in sorted_table}
    aggregates = _compute_aggregates(table)

    n = len(sorted_table)
    losers_count = n // 2
    neutros_count = n % 2
    losers_slice = sorted_table[n - losers_count :] if losers_count else []
    neutros_slice = (
        sorted_table[n - losers_count - neutros_count : n - losers_count]
        if neutros_count
        else []
    )

    return Palmares(
        temporada=season,
        campeon=_label(by_position.get(1)),
        subcampeon=_label(by_position.get(2)),
        tercero=_label(by_position.get(3)),
        multas=[_label(s) for s in losers_slice],
        neutros=[_label(s) for s in neutros_slice],
        puntuacion="personalizada",
        record_puntos=aggregates["record_puntos"],
        jornadas_ganadas=aggregates["jornadas_ganadas"],
        clausulazos_total=str(clausulazos_total),
        standings_table=table,
    )


def _label(s: SeasonStanding | None) -> str:
    if s is None:
        return ""
    return s.real_name or s.team_name or "—"


def _count_clauses(raw: dict) -> int:
    """Count real clausulazos in the transfer board.

    Biwenger's ``board?type=transfer`` returns every transfer event (regular
    market sales, clausulazos, etc.). A clausulazo is an item inside
    ``entry.content`` whose ``type`` is ``"clause"`` — mirroring the filter
    in ``packages/biwenger_tools/scraper_job/logic/processing.py``.
    """
    entries = raw.get("data", []) or []
    if isinstance(entries, dict):
        entries = list(entries.values())
    return sum(
        sum(1 for c in (entry.get("content") or []) if c.get("type") == "clause")
        for entry in entries
    )


def _parse_abandoned(values: list[str]) -> list[tuple[str, str, str]]:
    """Parse ``NAME=TEAM=REASON`` triples passed on the command line.

    The team slot may be empty (``Alberto==abandono``) when no equivalent
    Biwenger team name applies — the row then renders with ``"—"`` for
    the team column.
    """
    parsed = []
    for raw in values:
        parts = raw.split("=", 2)
        if len(parts) != 3:
            print(
                f"WARNING: --abandoned-user '{raw}' is malformed "
                "(need NAME=TEAM=REASON, team may be empty); skipped.",
                file=sys.stderr,
            )
            continue
        name, team, reason = (p.strip() for p in parts)
        parsed.append((name, team, reason))
    return parsed


def _write_to_firestore(palmares: Palmares, force: bool) -> bool:
    """Write to ``palmares/<season>``.

    Refuses to overwrite an existing doc unless ``force=True``. Returns True
    on success, False on any error or on a skipped overwrite.
    """
    try:
        from core.sdk.firestore import get_client
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: cannot import firestore client: {exc}", file=sys.stderr)
        return False
    try:
        doc_ref = get_client().collection("palmares").document(palmares.temporada)
        if doc_ref.get().exists and not force:
            print(
                f"SKIP: palmares/{palmares.temporada} already exists in Firestore. "
                "Pass --force to overwrite.",
                file=sys.stderr,
            )
            return False
        doc_ref.set(palmares.to_firestore())
        return True
    except Exception as exc:
        print(f"ERROR: Firestore write failed: {exc}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", help="Season being closed, e.g. 25-26")
    parser.add_argument(
        "--abandoned-user",
        action="append",
        default=[],
        metavar="NAME=TEAM=REASON",
        help="Append a row for an account deleted mid-season; repeatable. "
        "Example: --abandoned-user 'Alberto=#NOALOSCLAUSULAZOS=abandono'. "
        "Leave the team slot empty if not known: 'Someone==abandono'.",
    )
    parser.add_argument(
        "--write-firestore",
        action="store_true",
        help="Write the resulting doc to Firestore at palmares/<season>.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite palmares/<season> if it already exists. "
        "Without this flag, an existing doc is left untouched.",
    )
    args = parser.parse_args()

    email = os.getenv("BIWENGER_EMAIL", "")
    password = os.getenv("BIWENGER_PASSWORD", "")
    league_id = os.getenv("LEAGUE_ID", DEFAULT_LEAGUE_ID)
    if not all([email, password, league_id]):
        print(
            "ERROR: BIWENGER_EMAIL and BIWENGER_PASSWORD must be set "
            "(LEAGUE_ID defaults to core.constants.LEAGUE_ID).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        client = BiwengerClient(
            email=email,
            password=password,
            login_url=LOGIN_URL,
            account_url=ACCOUNT_URL,
            league_id=league_id,
        )
    except Exception as exc:
        print(f"ERROR: Biwenger authentication failed: {exc}", file=sys.stderr)
        print("Fill in the palmares rows manually.", file=sys.stderr)
        sys.exit(1)

    # --- Fetch the three reports in sequence ---
    try:
        standings = client.get_standings_full(league_standings_url(league_id))
    except Exception as exc:
        print(f"ERROR: standings fetch failed: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        rounds_rows = client.get_report_rows(league_round_report_url(league_id))
    except Exception as exc:
        print(f"WARNING: rounds report failed: {exc}", file=sys.stderr)
        rounds_rows = []

    try:
        points_rows = client.get_report_rows(league_round_points_report_url(league_id))
    except Exception as exc:
        print(f"WARNING: roundPoints report failed: {exc}", file=sys.stderr)
        points_rows = []

    try:
        clausulazos = client.get_all_clausulazos(clausulazos_url(league_id))
        clausulazos_total = _count_clauses(clausulazos)
    except Exception as exc:
        print(f"WARNING: clausulazos fetch failed: {exc}", file=sys.stderr)
        clausulazos_total = 0

    # --- Combine + abandoned-user injection ---
    table = _build_standings_table(standings, rounds_rows, points_rows)
    _append_abandoned(table, _parse_abandoned(args.abandoned_user))

    palmares = _build_palmares(args.season, table, clausulazos_total)

    # --- Output ---
    print("\n=== Firestore doc preview (palmares/{}) ===\n".format(args.season))
    print(json.dumps(palmares.to_firestore(), indent=2, ensure_ascii=False))

    print("\n=== Per-user table ===")
    for s in palmares.standings_table:
        note = f" [{s.note}]" if s.note else ""
        print(
            f"  {s.position}. {s.real_name or '—':10s} "
            f"({s.team_name})  pts={s.points}  best={s.best_round} "
            f"worst={s.worst_round}  wins={s.rounds_won} "
            f"avg_pos={s.avg_position:.1f}{note}"
        )

    if args.write_firestore:
        print("\nWriting to Firestore…")
        if _write_to_firestore(palmares, force=args.force):
            print(f"OK — palmares/{args.season} written.")
        else:
            sys.exit(1)
    else:
        print(
            "\nNot writing to Firestore (no --write-firestore). "
            "Rerun with the flag to push the doc."
        )


if __name__ == "__main__":
    main()
