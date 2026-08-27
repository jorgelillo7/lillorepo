"""Tests for the Liga H2H logic (reglamento chapter III).

Each test names the article it pins. The rules were read from the reglamento
and cross-checked against the organiser's spreadsheet formulas, not inferred.
"""

from packages.biwenger_tools.constants import H2H_MATCHDAYS, H2H_ROUNDS
from packages.biwenger_tools.web import h2h


def _rows(*fixtures) -> list[list[str]]:
    """Sheet rows in the organiser's column order, with a header on top."""
    header = [
        ["Calendario H2H"],
        ["Introduce los puntos"],
        ["Jornada", "Partido", "Equipo 1", "Puntos 1", "Puntos 2", "Equipo 2"],
    ]
    return header + [list(f) for f in fixtures]


def _round_one():
    """`(home, away)` of the three duels of matchday 1."""
    base = H2H_ROUNDS[0]
    return [base["p1"], base["p2"], base["p3"]]


# --- Scoring (art. 3.3) --------------------------------------------------


def test_draw_at_exactly_five_points_difference():
    """Art. 3.3 spells the boundary as «5 puntos o menos de diferencia», and
    the sheet's own `ABS(D-E)<=5` agrees. Five is a draw, six is a win — the
    off-by-one here would silently rewrite the whole table."""
    (home, away), _, _ = _round_one()

    five = h2h.Duel(partido=1, home=home, away=away, home_points=50, away_points=45)
    six = h2h.Duel(partido=1, home=home, away=away, home_points=51, away_points=45)

    assert five.outcome == "draw"
    assert six.outcome == "home"


def test_match_unplayed_when_one_score_missing():
    """The sheet guards every aggregate with `ISNUMBER(D)*ISNUMBER(E)`: a row
    with one score filled is someone mid-edit, not a result. Counting it would
    hand a 0–x thrashing to whoever was typed second."""
    (home, away), _, _ = _round_one()
    half = h2h.Duel(partido=1, home=home, away=away, home_points=70, away_points=None)

    assert not half.played
    assert half.outcome is None

    table = {
        s.equipo: s
        for s in h2h.standings([h2h.Round(jornada=1, duels=(half,), descansa="Manu")])
    }
    assert table[home].pj == 0
    assert table[away].pj == 0


def test_win_scores_three_and_draw_one():
    """Art. 3.3 — 3 / 1 / 0, and the loser still banks the points scored."""
    (a, b), (c, d), _ = _round_one()
    rounds = [
        h2h.Round(
            jornada=1,
            duels=(
                h2h.Duel(partido=1, home=a, away=b, home_points=78, away_points=43),
                h2h.Duel(partido=2, home=c, away=d, home_points=40, away_points=38),
            ),
            descansa="Manu",
        )
    ]
    table = {s.equipo: s for s in h2h.standings(rounds)}

    assert (table[a].puntos, table[a].pg, table[a].dif) == (3, 1, 35)
    assert (table[b].puntos, table[b].pp, table[b].dif) == (0, 1, -35)
    assert table[c].puntos == table[d].puntos == 1
    assert table[c].pe == table[d].pe == 1


# --- Tiebreaks (art. 3.4) ------------------------------------------------


def test_tiebreak_falls_back_to_victories():
    """Art. 3.4 orders points → difference → **victories**. The spreadsheet's
    own `SORTBY` uses points a favor as its third key instead, which is why the
    classification is computed here and never read from the sheet.

    Manu takes a win and a loss; Rubén takes three draws. Both land on three
    points and a difference of zero, so only the victory count can separate
    them — and Rubén is the earlier of the two in calendar order, so a stable
    sort with the third key missing would put him first.
    """
    winner, drawer = "Manu", "Rubén"
    assert h2h.teams().index(drawer) < h2h.teams().index(winner)

    def duel(partido, home, away, hp, ap):
        return h2h.Duel(
            partido=partido, home=home, away=away, home_points=hp, away_points=ap
        )

    rounds = [
        h2h.Round(  # Fabio – Rubén, drawn
            jornada=1,
            duels=(duel(1, "Fabio", drawer, 50, 50),),
            descansa=H2H_ROUNDS[0]["descansa"],
        ),
        h2h.Round(  # Manu beats Javi by twenty
            jornada=3,
            duels=(duel(2, winner, "Javi", 60, 40),),
            descansa=H2H_ROUNDS[2]["descansa"],
        ),
        h2h.Round(  # Pablo – Rubén drawn, and Manu gives the twenty back
            jornada=4,
            duels=(
                duel(1, "Pablo", drawer, 50, 50),
                duel(3, winner, "Fabio", 30, 50),
            ),
            descansa=H2H_ROUNDS[3]["descansa"],
        ),
        h2h.Round(  # Javi – Rubén, drawn
            jornada=5,
            duels=(duel(1, "Javi", drawer, 50, 50),),
            descansa=H2H_ROUNDS[4]["descansa"],
        ),
    ]

    table = {s.equipo: s for s in h2h.standings(rounds)}

    assert table[winner].puntos == table[drawer].puntos == 3
    assert table[winner].dif == table[drawer].dif == 0
    assert (table[winner].pg, table[drawer].pg) == (1, 0)
    assert table[winner].position < table[drawer].position


def test_unbreakable_tie_is_flagged_not_invented():
    """Criterion 3  («puntuación total en la Liga Regular») is not in this
    sheet and criterion 4 is a manual draw. Two presidents level on all three
    computable keys get a marker, not a fabricated rank."""
    (a, b), (c, d), (e, f) = _round_one()
    rounds = [
        h2h.Round(
            jornada=1,
            duels=(
                h2h.Duel(partido=1, home=a, away=b, home_points=60, away_points=40),
                h2h.Duel(partido=2, home=c, away=d, home_points=60, away_points=40),
                h2h.Duel(partido=3, home=e, away=f, home_points=70, away_points=30),
            ),
            descansa=H2H_ROUNDS[0]["descansa"],
        )
    ]
    table = {s.equipo: s for s in h2h.standings(rounds)}

    # Same points, same difference, same wins — and nothing left to separate
    # them without the Liga Regular totals.
    assert table[a].tie_unresolved and table[c].tie_unresolved
    # A bigger win breaks the tie on difference, so this one is a real rank.
    assert not table[e].tie_unresolved


# --- Reading the sheet ---------------------------------------------------


def test_parse_rows_ignores_everything_that_is_not_a_fixture():
    """The classification block sits to the right of the fixtures in the same
    tab, and the sheet has three header rows. The parser locates the fixture
    block by shape — two leading numbers — so neither has to be excluded by
    hard-coded coordinates that a single inserted row would break."""
    (home, away), _, _ = _round_one()
    rows = _rows(("1", "1", home, "78", "43", away, "G1", "Manu"))
    rows.append(["", "", "", "", "", "", "", "", "", "Pos.", "Equipo", "PJ"])

    matches, issues = h2h.parse_rows(rows)

    assert list(matches) == [(1, 1)]
    assert matches[(1, 1)].home_points == 78
    assert issues == []


def test_parse_rows_reads_spanish_and_float_formatted_scores():
    """Sheets hands back display strings, so `78`, `78.0` and `78,0` all have
    to land on the same integer."""
    (home, away), _, _ = _round_one()
    rows = _rows(("2", "1", home, "78,0", "43.0", away))

    matches, _ = h2h.parse_rows(rows)

    assert (matches[(2, 1)].home_points, matches[(2, 1)].away_points) == (78, 43)


def test_scores_follow_the_pairing_not_the_column_order():
    """The organiser may type a duel the other way round. The calendar decides
    who is listed first; the scores swap to follow it."""
    (home, away), _, _ = _round_one()
    matches, _ = h2h.parse_rows(_rows(("1", "1", away, "43", "78", home)))

    rounds, issues = h2h.build_rounds(matches)
    duel = rounds[0].duels[0]

    assert issues == []
    assert (duel.home, duel.home_points) == (home, 78)
    assert (duel.away, duel.away_points) == (away, 43)


def test_unknown_fixture_in_sheet_is_reported_not_rendered():
    """A row naming a pairing the calendar does not have means the sheet was
    reordered. Dropping the scores loudly beats landing them on the wrong
    duel for the rest of the season."""
    (home, _away), _, _ = _round_one()
    matches, _ = h2h.parse_rows(_rows(("1", "1", home, "78", "43", "Nadie")))

    rounds, issues = h2h.build_rounds(matches)

    assert not rounds[0].duels[0].played
    assert len(issues) == 1 and "J1 partido 1" in issues[0]


def test_duplicate_row_is_reported():
    """Two rows for the same duel: the first wins and the second is named."""
    (home, away), _, _ = _round_one()
    matches, issues = h2h.parse_rows(
        _rows(
            ("1", "1", home, "78", "43", away),
            ("1", "1", home, "10", "10", away),
        )
    )

    assert matches[(1, 1)].home_points == 78
    assert len(issues) == 1 and "duplicada" in issues[0]


def test_build_rounds_covers_the_whole_season_without_a_sheet():
    """No scores at all still yields the full 35-matchday calendar. This is
    what the page falls back to when the Sheets credential dies — which it
    did, for a whole season, without anybody noticing."""
    rounds, issues = h2h.build_rounds({})

    assert len(rounds) == H2H_MATCHDAYS
    assert issues == []
    assert all(len(r.duels) == 3 for r in rounds)
    assert not any(r.started for r in rounds)
    # The seven-round base repeats: matchday 8 rests whoever matchday 1 did.
    assert rounds[0].descansa == rounds[7].descansa


def test_every_president_rests_once_per_cycle():
    """Seven presidents, seven rounds, three duels each — so each cycle every
    president plays six times and rests once. A calendar that fails this is
    not a valid round robin."""
    assert len(h2h.teams()) == 7

    playing = [
        name
        for r in h2h.build_rounds({})[0][:7]
        for d in r.duels
        for name in (d.home, d.away)
    ]
    resting = [r.descansa for r in h2h.build_rounds({})[0][:7]]

    assert sorted(resting) == sorted(h2h.teams())
    assert all(playing.count(name) == 6 for name in h2h.teams())
