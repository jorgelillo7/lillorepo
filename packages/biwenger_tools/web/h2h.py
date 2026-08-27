"""Liga H2H — fixtures, results and standings (reglamento chapter III).

Pure functions: no I/O, no Flask, no Sheets client. The route fetches the
organiser's spreadsheet and hands the raw cell rows in here.

The spreadsheet is treated as an **input form, not a data source**: only the
two score cells per match are read. Everything else — who plays whom, the
result of each duel, the whole classification — is derived here from
`constants.H2H_ROUNDS` and the articles below. The sheet computes its own
classification with a `SORTBY` that renders `#NAME?` and sorts by a criterion
the reglamento does not use, which is exactly why it is not read.

Articles this encodes:
- 3.1 — 35 matchdays, calendar fixed before the season (`H2H_ROUNDS`).
- 3.3 — win 3, draw 1, loss 0; a gap of **five points or fewer is a draw**.
- 3.4 — tiebreaks: points → difference → wins → total Liga Regular → draw.
  The fourth is manual and the third is not computable from this sheet, so
  a tie surviving the first three is reported, not silently ordered.
"""

from collections import Counter
from dataclasses import dataclass, field

from packages.biwenger_tools.constants import H2H_MATCHDAYS, H2H_ROUNDS

# Art. 3.3. Five exactly is a draw, not a win — the boundary is inclusive.
DRAW_MARGIN = 5
POINTS_WIN = 3
POINTS_DRAW = 1

_DUEL_KEYS = ("p1", "p2", "p3")


@dataclass(frozen=True)
class SheetMatch:
    """One fixture row as the organiser typed it."""

    jornada: int
    partido: int
    home: str
    away: str
    home_points: int | None
    away_points: int | None


@dataclass(frozen=True)
class Duel:
    """One duel of a matchday, with the scores overlaid when they exist."""

    partido: int
    home: str
    away: str
    home_points: int | None = None
    away_points: int | None = None

    @property
    def played(self) -> bool:
        """Art. 3.3 — a duel counts only once **both** scores are in.

        A half-filled row is someone mid-edit, not a result.
        """
        return self.home_points is not None and self.away_points is not None

    @property
    def outcome(self) -> str | None:
        """``"home"``, ``"away"``, ``"draw"``, or ``None`` when unplayed."""
        if not self.played:
            return None
        if abs(self.home_points - self.away_points) <= DRAW_MARGIN:
            return "draw"
        return "home" if self.home_points > self.away_points else "away"


@dataclass(frozen=True)
class Round:
    """A matchday: three duels and the president who rests."""

    jornada: int
    duels: tuple[Duel, ...]
    descansa: str

    @property
    def played(self) -> bool:
        return all(d.played for d in self.duels)

    @property
    def started(self) -> bool:
        return any(d.played for d in self.duels)


@dataclass
class Standing:
    """One row of the classification. Counters are accumulated, not read."""

    equipo: str
    pj: int = 0
    pg: int = 0
    pe: int = 0
    pp: int = 0
    pf: int = 0
    pc: int = 0
    position: int = 0
    tie_unresolved: bool = False
    form: list[str] = field(default_factory=list)

    @property
    def dif(self) -> int:
        return self.pf - self.pc

    @property
    def puntos(self) -> int:
        return self.pg * POINTS_WIN + self.pe * POINTS_DRAW


def teams() -> tuple[str, ...]:
    """Every president in the competition, in first-appearance order.

    Derived from the calendar rather than listed again, so adding a manager
    means editing one place.
    """
    seen: list[str] = []
    for base in H2H_ROUNDS:
        for key in _DUEL_KEYS:
            for name in base[key]:
                if name not in seen:
                    seen.append(name)
        if base["descansa"] not in seen:
            seen.append(base["descansa"])
    return tuple(seen)


def _to_int(cell: str | None) -> int | None:
    """A score cell, or ``None`` when it is blank or not a number.

    Sheets hands back display strings, so `"78"`, `"78.0"` and the Spanish
    `"78,0"` all have to land on the same integer.
    """
    text = (cell or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_rows(
    rows: list[list[str]],
) -> tuple[dict[tuple[int, int], SheetMatch], list[str]]:
    """Fixture rows keyed by ``(jornada, partido)``, plus what was rejected.

    Self-locating: any row whose first two cells are not both numbers is
    skipped in silence, so headers, blank separators and the classification
    block sitting to the right of the fixtures all fall away on their own.
    A row that *does* look like a fixture but duplicates an earlier key is
    reported — that one is a real edit mistake.
    """
    matches: dict[tuple[int, int], SheetMatch] = {}
    issues: list[str] = []

    for row in rows:
        cells = [(c or "").strip() for c in row] + [""] * 8
        jornada, partido = _to_int(cells[0]), _to_int(cells[1])
        if jornada is None or partido is None:
            continue

        key = (jornada, partido)
        if key in matches:
            issues.append(f"J{jornada} partido {partido}: fila duplicada, se ignora")
            continue

        matches[key] = SheetMatch(
            jornada=jornada,
            partido=partido,
            home=cells[2],
            away=cells[5],
            home_points=_to_int(cells[3]),
            away_points=_to_int(cells[4]),
        )

    return matches, issues


def build_rounds(
    matches: dict[tuple[int, int], SheetMatch],
) -> tuple[list[Round], list[str]]:
    """The full 35-matchday calendar with the sheet's scores overlaid.

    The calendar always comes from `H2H_ROUNDS`; the sheet only contributes
    numbers. Its `Equipo 1` / `Equipo 2` columns are read as a **checksum**:
    if a row names a different pairing than the calendar does, its scores are
    dropped and the mismatch is reported. That is what stops a reordered row
    from landing 78–43 on the wrong duel — silently, and for the rest of the
    season.
    """
    rounds: list[Round] = []
    issues: list[str] = []

    for index in range(H2H_MATCHDAYS):
        jornada = index + 1
        base = H2H_ROUNDS[index % len(H2H_ROUNDS)]
        duels: list[Duel] = []

        for partido, key in enumerate(_DUEL_KEYS, start=1):
            home, away = base[key]
            match = matches.get((jornada, partido))
            if match and {match.home, match.away} != {home, away}:
                issues.append(
                    f"J{jornada} partido {partido}: la hoja dice "
                    f"«{match.home} – {match.away}» y el calendario "
                    f"«{home} – {away}»; se ignoran esos puntos"
                )
                match = None
            # The sheet may list the pair the other way round; keep the
            # calendar's order and swap the scores to match it.
            if match and match.home == away:
                points = (match.away_points, match.home_points)
            elif match:
                points = (match.home_points, match.away_points)
            else:
                points = (None, None)
            duels.append(
                Duel(
                    partido=partido,
                    home=home,
                    away=away,
                    home_points=points[0],
                    away_points=points[1],
                )
            )

        rounds.append(
            Round(jornada=jornada, duels=tuple(duels), descansa=base["descansa"])
        )

    known = {(r.jornada, d.partido) for r in rounds for d in r.duels}
    for jornada, partido in sorted(set(matches) - known):
        issues.append(
            f"J{jornada} partido {partido}: no existe en el calendario, se ignora"
        )

    return rounds, issues


def standings(rounds: list[Round]) -> list[Standing]:
    """The classification, ordered by art. 3.4 and numbered from 1.

    Tiebreaks applied here are points → difference → wins. The reglamento's
    next criterion is the season's total Liga Regular score, which this
    spreadsheet does not carry, and the one after that is a manual draw — so
    presidents still level after three are flagged `tie_unresolved` and left
    in calendar order rather than being given an invented rank.
    """
    table = {name: Standing(equipo=name) for name in teams()}

    for round_ in rounds:
        for duel in round_.duels:
            if not duel.played:
                continue
            home, away = table.get(duel.home), table.get(duel.away)
            if home is None or away is None:
                continue
            for side, own, against in (
                (home, duel.home_points, duel.away_points),
                (away, duel.away_points, duel.home_points),
            ):
                side.pj += 1
                side.pf += own
                side.pc += against
            if duel.outcome == "draw":
                home.pe += 1
                away.pe += 1
                home.form.append("E")
                away.form.append("E")
            else:
                winner, loser = (home, away) if duel.outcome == "home" else (away, home)
                winner.pg += 1
                loser.pp += 1
                winner.form.append("G")
                loser.form.append("P")

    # Python's sort is stable, so anything the key cannot separate keeps the
    # calendar order it went in with — deterministic, and never a fake rank.
    ordered = sorted(table.values(), key=lambda s: (-s.puntos, -s.dif, -s.pg))
    for position, entry in enumerate(ordered, start=1):
        entry.position = position

    ranked = Counter((s.puntos, s.dif, s.pg) for s in ordered)
    for entry in ordered:
        entry.tie_unresolved = ranked[(entry.puntos, entry.dif, entry.pg)] > 1

    return ordered
