"""How much a fixture moves a player's points: each appearance against a given
opponent, measured against the same player's own mean in his other games.

Pure. Reads Biwenger round payloads (`games[].home/away.reports[].points`)
that the caller fetched; the scoring system is whatever those were fetched
with. How to read the output: `docs/technical/backend/projection-ledger.md`.
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass

# The opponents under suspicion. Left out of every baseline, so a bad
# afternoon against one cannot lower the bar the other is measured against.
WATCHED = ("Barcelona", "Real Madrid")

# Fewer other games than this and a player's "usual" is one or two
# afternoons, not a mean.
MIN_OTHER_GAMES = 3


@dataclass(frozen=True)
class Appearance:
    player_id: int | None
    name: str | None
    position: int | None
    team: str | None
    opponent: str | None
    home: bool
    points: int
    round_id: int | None
    round_name: str | None
    game_id: int | None


def appearances(rounds: list[dict]) -> list[Appearance]:
    """Every scored report of every finished game, each game once.

    Biwenger lists a postponed matchday's games under the original round and
    again under each "aplazada" id, so games are deduplicated by their id;
    the first round that lists one names it.
    """
    seen: set = set()
    out: list[Appearance] = []
    for rnd in rounds:
        for game in rnd.get("games") or []:
            if game.get("status") != "finished" or game.get("id") in seen:
                continue
            seen.add(game.get("id"))
            for side, other in (("home", "away"), ("away", "home")):
                team, opp = game.get(side) or {}, game.get(other) or {}
                for report in team.get("reports") or []:
                    if report.get("points") is None:
                        continue
                    player = report.get("player") or {}
                    out.append(
                        Appearance(
                            player_id=player.get("id"),
                            name=player.get("name"),
                            position=player.get("position"),
                            team=team.get("name"),
                            opponent=opp.get("name"),
                            home=side == "home",
                            points=report["points"],
                            round_id=rnd.get("id"),
                            round_name=rnd.get("name"),
                            game_id=game.get("id"),
                        )
                    )
    return out


def _by_player(apps: list[Appearance]) -> dict[int | None, list[Appearance]]:
    grouped: dict[int | None, list[Appearance]] = defaultdict(list)
    for app in apps:
        grouped[app.player_id].append(app)
    return grouped


def opponent_deltas(
    apps: list[Appearance], opponent: str, positions: set
) -> list[tuple[float, Appearance]]:
    """`(points − own mean elsewhere, appearance)` for each appearance of a
    player in `positions` against `opponent`. "Elsewhere" excludes every
    `WATCHED` opponent; a player with fewer than `MIN_OTHER_GAMES` there is
    left out."""
    grouped = _by_player(apps)
    out = []
    for app in apps:
        if app.opponent != opponent or app.position not in positions:
            continue
        others = [a.points for a in grouped[app.player_id] if a.opponent not in WATCHED]
        if len(others) < MIN_OTHER_GAMES:
            continue
        out.append((app.points - statistics.mean(others), app))
    return out


def summarize(deltas: list[tuple[float, object]]) -> dict | None:
    """`{n, mean, median, below}` of the deltas — `below` counts how many
    scored under their own mean — or `None` for an empty sample."""
    values = [d for d, _ in deltas]
    if not values:
        return None
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "below": sum(1 for v in values if v < 0),
    }


def by_match(deltas: list[tuple[float, Appearance]]) -> list[dict]:
    """The deltas averaged per team and game, worst first. Appearances in one
    game are not independent — one heavy defeat sinks a whole back line — so
    this is the count to read before the per-appearance one."""
    grouped: dict[tuple, list[float]] = defaultdict(list)
    for delta, app in deltas:
        grouped[(app.game_id, app.round_name, app.team, app.home)].append(delta)
    rows = [
        {
            "round_name": round_name,
            "team": team,
            "home": home,
            "n": len(values),
            "mean": statistics.mean(values),
        }
        for (_, round_name, team, home), values in grouped.items()
    ]
    return sorted(rows, key=lambda row: row["mean"])


def jp_vs_real(
    apps: list[Appearance],
    league_jp: dict[int, dict[str, int]],
    opponent: str,
    positions: set,
) -> list[tuple[float, float, Appearance]]:
    """`(jp delta, real delta, appearance)` against `opponent`, on the rounds
    whose capture holds Jornada Perfecta's projection for the player.

    Both deltas use the same baseline rounds — the player's other rounds with
    a projection, `WATCHED` opponents excluded — so the pair says whether the
    projection moved with the fixture as much as the points did.
    `league_jp` is `{round_id: {str(bw_id): jp_sf}}`.
    """
    scored: list[tuple[Appearance, int]] = []
    for app in apps:
        projected = league_jp.get(app.round_id) if app.round_id is not None else None
        jp = (projected or {}).get(str(app.player_id))
        if jp is not None:
            scored.append((app, jp))
    grouped: dict[int | None, list[tuple[Appearance, int]]] = defaultdict(list)
    for app, jp in scored:
        grouped[app.player_id].append((app, jp))

    out = []
    for app, jp in scored:
        if app.opponent != opponent or app.position not in positions:
            continue
        others = [
            (a.points, j)
            for a, j in grouped[app.player_id]
            if a.opponent not in WATCHED
        ]
        if len(others) < MIN_OTHER_GAMES:
            continue
        jp_delta = jp - statistics.mean(j for _, j in others)
        real_delta = app.points - statistics.mean(p for p, _ in others)
        out.append((jp_delta, real_delta, app))
    return out
