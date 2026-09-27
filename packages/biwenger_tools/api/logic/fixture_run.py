"""How hard each team's next few fixtures are, from Biwenger's own ratings.

Every pending game on `cf.biwenger.com/rounds/la-liga/{id}` carries, per
side, `difficulty.rating` (0–100, higher is harder): the difficulty *that
side faces*. This module turns a handful of those rounds into a per-team run
of upcoming ratings and a short label for the market images.

Display only — nothing here feeds a bid, a clause or an offer decision.
Spec: `openspec/specs/biwenger_tools/team-analysis/spec.md`.
"""

from statistics import mean

GAMES_AHEAD = 5
COLUMN = "Calendario ({n})"
COLUMN_UNAVAILABLE = "Calendario (sin datos)"
# Five games averaged pull toward the middle: at 40/60 no team in LaLiga read
# "difícil". 45/55 split the twenty 10 / 8 / 2 on the day it shipped.
_EASY_BELOW = 45
_HARD_ABOVE = 55
_OPEN_ROUNDS = ("active", "pending")


def rounds_to_read(current: dict) -> list[int]:
    """Ids of the season's open rounds, in the order Biwenger lists them.

    That order is not chronological — a postponed round sits among later
    ones — which is why callers sort games by kickoff, never by round.
    """
    rounds = ((current or {}).get("season") or {}).get("rounds") or []
    return [r["id"] for r in rounds if r.get("status") in _OPEN_ROUNDS]


def upcoming_by_team(rounds: list[dict], now: float) -> dict[int, list[int]]:
    """`{team_id: [rating, …]}` over the games still to be played, soonest
    first. A game without a published rating is left out rather than
    guessed; a played game never counts."""
    dated: dict[int, list[tuple[int, int]]] = {}
    for round_data in rounds:
        for game in round_data.get("games") or []:
            if game.get("status") == "finished" or (game.get("date") or 0) <= now:
                continue
            for side in ("home", "away"):
                team = game.get(side) or {}
                rating = (team.get("difficulty") or {}).get("rating")
                if team.get("id") is None or rating is None:
                    continue
                dated.setdefault(team["id"], []).append((game["date"], int(rating)))
    return {
        team: [rating for _, rating in sorted(games)] for team, games in dated.items()
    }


def next_ratings(upcoming: dict[int, list[int]], team_id, n: int) -> list[int]:
    return (upcoming.get(team_id) or [])[:n]


def label(ratings: list[int]) -> str:
    """`"fácil 31"`, `"medio 48"`, `"difícil 67"` — the rounded average with
    its band — or `"—"` when there is nothing to average."""
    if not ratings:
        return "—"
    avg = int(mean(ratings) + 0.5)  # half up; round() goes to even
    band = "fácil" if avg < _EASY_BELOW else "difícil" if avg > _HARD_ABOVE else "medio"
    return f"{band} {avg}"


def column_for(upcoming: dict | None, n: int = GAMES_AHEAD) -> str:
    """The column header `annotate` writes under, known before the rows are."""
    return COLUMN_UNAVAILABLE if upcoming is None else COLUMN.format(n=n)


def annotate(rows: list[dict], upcoming: dict | None, n: int = GAMES_AHEAD) -> str:
    """Write each row's label under the returned column name, in place.

    `upcoming=None` means the calendar could not be read: the column says so
    in its header, so a failed read never passes for "no games ahead".
    """
    column = column_for(upcoming, n)
    for row in rows:
        row[column] = (
            "—"
            if upcoming is None
            else label(next_ratings(upcoming, row.get("team_id"), n))
        )
    return column
