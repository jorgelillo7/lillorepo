"""Unit tests for `api/logic/rebuild.py`."""

from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import draft, rebuild
from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID

# --- fixtures --------------------------------------------------------------


def _squad(gk=0, d=0, m=0, f=0):
    """Squad rows carrying only what `eligibilities` reads."""
    rows = [{"position_id": GK, "alt_positions": []}] * gk
    rows += [{"position_id": DEF, "alt_positions": []}] * d
    rows += [{"position_id": MID, "alt_positions": []}] * m
    rows += [{"position_id": FWD, "alt_positions": []}] * f
    return rows


def _candidate(bw_id, pos, clause, sf=300, alt=None):
    return {
        "bw_id": bw_id,
        "name": f"P{bw_id}",
        "position_id": pos,
        "alt_positions": alt or [],
        "jp_player": {"predict": [{"type": 2, "rate": sf}]},
        "clause_value": clause,
    }


def _lines(gk=0, d=0, m=0, f=0, hybrids=()):
    """Eligibility sets for a squad. `hybrids` takes explicit line tuples.

    Mirrors `test_draft.py`'s `_lines` helper so both suites read the same
    fixtures for the same underlying primitive.
    """
    squad = [frozenset({GK})] * gk
    squad += [frozenset({DEF})] * d
    squad += [frozenset({MID})] * m
    squad += [frozenset({FWD})] * f
    return squad + [frozenset(h) for h in hybrids]


# --- eligibilities -----------------------------------------------------------


def test_eligibilities_builds_frozensets_from_primary_and_alt_positions():
    rows = [
        {"position_id": DEF, "alt_positions": [MID]},
        {"position_id": FWD, "alt_positions": []},
    ]
    assert rebuild.eligibilities(rows) == [frozenset({DEF, MID}), frozenset({FWD})]


def test_eligibilities_drops_lines_outside_gk_def_mid_fwd():
    """Biwenger reports a coach as position 5. An unfiltered eligibility set
    lets `draft._shortfall`'s min-cut treat him as usable inside any subset
    of lines, understating the deficit the rebuild trigger depends on —
    mirrors the guard `draft.eligible_lines` already applies."""
    rows = [{"position_id": 5, "alt_positions": []}]
    assert rebuild.eligibilities(rows) == [frozenset()]


# --- line_deficit ------------------------------------------------------------


_SQUADS_FOR_INVARIANT = [
    _lines(gk=1, d=4, m=4, f=2),
    _lines(gk=0, d=5, m=4, f=2),
    _lines(gk=1, d=2, m=5, f=4),
    _lines(gk=1, d=4, hybrids=[(FWD, MID)] * 6),
    _lines(gk=2, d=3, m=3, f=3, hybrids=[(DEF, MID), (MID, FWD)]),
    [],
]


def test_line_deficit_sums_to_the_shortfall_draft_already_computes():
    """`line_deficit` is a second, per-line implementation of the max flow
    `draft._shortfall` already reduces to a single count. The two must never
    disagree on the total — checked against every one of the 14 formations,
    over squads that include multi-position players, since a per-line count
    that is not a real matching is exactly the case that would break only
    there."""
    for elig in _SQUADS_FOR_INVARIANT:
        for requirement in draft._requirements():
            assert sum(rebuild.line_deficit(elig, requirement).values()) == (
                draft._shortfall(elig, requirement)
            )


def test_line_deficit_matches_a_simple_squad_by_hand():
    elig = _lines(gk=1, d=2, m=4, f=2)
    requirement = {GK: 1, DEF: 4, MID: 3, FWD: 3}
    assert rebuild.line_deficit(elig, requirement) == {GK: 0, DEF: 2, MID: 0, FWD: 1}


def test_line_deficit_lets_two_hybrids_fill_both_short_lines():
    """Two DEF/MID players can close a DEF hole and a MID hole between them,
    even though neither line's requirement can be read off a single player."""
    elig = [frozenset({DEF, MID}), frozenset({DEF, MID})]
    requirement = {GK: 0, DEF: 1, MID: 1, FWD: 0}
    assert rebuild.line_deficit(elig, requirement) == {GK: 0, DEF: 0, MID: 0, FWD: 0}


def test_line_deficit_attributes_a_single_hybrids_hole_by_search_order():
    """One DEF/MID player can only close one of two holes. Which one is a
    documented implementation detail (see `line_deficit`'s docstring): the
    line tried first in `requirement`'s own key order wins, here DEF before
    MID."""
    elig = [frozenset({DEF, MID})]
    requirement = {GK: 0, DEF: 1, MID: 1, FWD: 0}
    assert rebuild.line_deficit(elig, requirement) == {GK: 0, DEF: 0, MID: 1, FWD: 0}


# --- value_of ----------------------------------------------------------------


def _row_with_sf(sf, clause):
    return {"jp_player": {"predict": [{"type": 2, "rate": sf}]}, "clause_value": clause}


def test_value_of_is_predicted_points_per_euro_of_clause():
    row = _row_with_sf(sf=400, clause=8_000_000)
    assert rebuild.value_of(row) == 400 / 8_000_000


def test_value_of_ranks_a_cheaper_worse_player_above_an_expensive_star():
    cheap = _row_with_sf(sf=200, clause=2_000_000)
    star = _row_with_sf(sf=600, clause=40_000_000)
    assert rebuild.value_of(cheap) > rebuild.value_of(star)


# --- target_formation ---------------------------------------------------------


def test_target_formation_breaks_ties_by_the_cheapest_affordable_line():
    """Squad missing every outfielder: every formation needs the same ten
    outfield signings, so the count alone cannot break the tie. Only 3-4-3
    is left reachable once DEF and MID have no affordable candidate at all
    — every other formation needing DEF or MID prices out to infinity."""
    elig = rebuild.eligibilities(_squad(gk=1))
    affordable = [
        _candidate(1, FWD, clause=5_000_000, sf=300),
    ]
    requirement, count = rebuild.target_formation(elig, affordable)
    assert requirement == {GK: 1, DEF: 3, MID: 4, FWD: 3}
    assert count == 10


def test_target_formation_treats_an_unaffordable_line_as_unreachable_not_free():
    """A formation whose only deficit line has nobody affordable must lose
    to one whose deficit lines are all coverable, even if the unreachable
    formation would otherwise need fewer signings — flagged in the
    docstring precisely so a future edit does not "optimise" this into
    treating a missing line as a zero-cost line."""
    elig = rebuild.eligibilities(_squad(gk=1, d=3, m=4, f=2))  # 3-4-3 minus 1 FWD
    affordable = [_candidate(1, DEF, clause=1_000_000, sf=300)]  # no FWD candidate
    requirement, count = rebuild.target_formation(elig, affordable)
    assert count == 1
    # 3-4-3 is one FWD short and nothing can fill it; 4-4-2 is one DEF short
    # and the pool covers that. The chosen formation's deficit must land where
    # there is something to buy.
    deficit = rebuild.line_deficit(elig, requirement)
    assert {line for line, missing in deficit.items() if missing} == {DEF}


# --- build_plan: reserving and starving -------------------------------------


def test_the_plan_reserves_the_cheapest_candidate_for_every_remaining_hole():
    """Two DEF holes, three DEF candidates. The reservation set aside for
    each hole is always the cheapest *still-unclaimed* body, never the same
    one counted twice.

    `reserve_floor` is that budgeting artefact, not what gets spent — the
    winner is chosen by points-per-euro and can cost more (see the two
    distinct `bw_id`s bought below for exactly that)."""
    my_rows = _squad(gk=1, d=1, m=6, f=5)  # every d=3 formation: DEF short by 2
    pool = [
        _candidate(1, DEF, clause=5_000_000, sf=300),
        _candidate(2, DEF, clause=8_000_000, sf=560),
        _candidate(3, DEF, clause=20_000_000, sf=1000),
    ]
    plan = rebuild.build_plan(
        my_rows=my_rows, affordable=pool, cash=40_000_000, floor=0, bench=0
    )
    assert plan.completes_xi is True
    assert [s.reserve_floor for s in plan.signings] == [5_000_000, 5_000_000]
    assert len({s.row["bw_id"] for s in plan.signings}) == 2


def test_reserve_floor_is_not_what_gets_spent_and_must_not_be_read_as_a_ceiling():
    """The bug this pins: `reserve_floor` is the cheapest candidate's price
    at commit time, but the winner is chosen by points-per-euro and is
    routinely pricier. A caller that reads `reserve_floor` as "the most this
    signing can cost" excludes its own approved target on essentially every
    real plan — this asserts the two numbers can legitimately differ."""
    my_rows = _squad(gk=1, d=1, m=6, f=5)
    pool = [
        _candidate(1, DEF, clause=5_000_000, sf=300),
        _candidate(2, DEF, clause=8_000_000, sf=560),
        _candidate(3, DEF, clause=20_000_000, sf=1000),
    ]
    plan = rebuild.build_plan(
        my_rows=my_rows, affordable=pool, cash=40_000_000, floor=0, bench=0
    )
    first = plan.signings[0]
    assert first.row["clause_value"] == 8_000_000  # the actual cost
    assert first.reserve_floor == 5_000_000  # the unrelated budgeting figure
    assert first.row["clause_value"] > first.reserve_floor


def test_a_star_signing_is_refused_when_it_would_starve_the_other_holes():
    """One 40M star DEF + two 5M MID holes on 45M cash: buying the star would
    leave nothing for the MID holes it does not fill, so the reserve forces a
    cheaper DEF instead. The whole plan costs 16M and the star alone costs 40M
    — greedy-by-points buys the star and strands the eleven."""
    # 8 players. With no forward affordable, every FWD-deficit formation is
    # unreachable, so the cheapest reachable shape is 3-4-3: one DEF and two
    # MID short. Three holes, which is what gives the star something to starve.
    my_rows = _squad(gk=1, d=2, m=2, f=3)
    star = _candidate(1, DEF, clause=40_000_000, sf=2000)
    backup = _candidate(2, DEF, clause=6_000_000, sf=300)
    mids = [
        _candidate(10, MID, clause=5_000_000, sf=250),
        _candidate(11, MID, clause=5_000_000, sf=250),
    ]
    pool = [star, backup] + mids
    plan = rebuild.build_plan(
        my_rows=my_rows, affordable=pool, cash=45_000_000, floor=0, bench=0
    )
    bought_ids = {s.row["bw_id"] for s in plan.signings}
    assert 1 not in bought_ids
    assert 2 in bought_ids
    assert plan.completes_xi is True


def test_the_plan_fills_the_positions_that_block_every_formation_first():
    """DEF (needed by every formation) is filled before FWD (skippable via
    `4-6-0`), even though both are short in the chosen formation."""
    my_rows = _squad(gk=1, d=1, m=3, f=1)
    pool = [
        _candidate(1, DEF, clause=5_000_000, sf=300),
        _candidate(2, DEF, clause=7_000_000, sf=400),
        _candidate(3, DEF, clause=9_000_000, sf=500),
        _candidate(4, FWD, clause=4_000_000, sf=260),
        _candidate(5, FWD, clause=6_000_000, sf=400),
        # No MID candidate at all: any formation still short a midfielder
        # prices out to infinity, leaving only the DEF+FWD formations in
        # play — see `test_target_formation_breaks_ties_...` for the same
        # mechanism in isolation.
    ]
    plan = rebuild.build_plan(
        my_rows=my_rows, affordable=pool, cash=100_000_000, floor=0, bench=0
    )
    assert plan.formation == "4-3-3"
    assert [s.line for s in plan.signings] == [DEF, DEF, DEF, FWD, FWD]
    assert plan.completes_xi is True


def test_the_plan_ranks_by_points_per_euro_when_money_is_the_constraint():
    """A cheaper, worse-SF candidate with the better points-per-euro ratio
    wins over a pricier, higher-SF one."""
    my_rows = _squad(gk=1, d=2, m=6, f=5)  # DEF short by 1, nothing else
    worse_ratio_higher_sf = _candidate(1, DEF, clause=10_000_000, sf=700)
    better_ratio_lower_sf = _candidate(2, DEF, clause=5_000_000, sf=400)
    pool = [worse_ratio_higher_sf, better_ratio_lower_sf]
    plan = rebuild.build_plan(
        my_rows=my_rows, affordable=pool, cash=50_000_000, floor=0, bench=0
    )
    assert len(plan.signings) == 1
    assert plan.signings[0].row["bw_id"] == 2


# --- build_plan: goalkeepers and unreachable elevens ------------------------


def _gk_less_squad_pool():
    my_rows = _squad(gk=0, d=5, m=6, f=5)  # every outfield line maxed out
    pool = [
        _candidate(1, GK, clause=1_000_000, sf=999),  # tempting on SF alone
        _candidate(2, DEF, clause=2_000_000, sf=999),
    ]
    return my_rows, pool


def test_the_plan_never_buys_a_goalkeeper():
    my_rows, pool = _gk_less_squad_pool()
    plan = rebuild.build_plan(
        my_rows=my_rows, affordable=pool, cash=50_000_000, floor=0, bench=2
    )
    assert all(s.row.get("position_id") != GK for s in plan.signings)
    assert all(s.line != GK for s in plan.signings)


def test_the_plan_states_when_it_cannot_reach_a_legal_xi():
    """A squad with zero goalkeepers can never field an eleven through this
    planner — GK is excluded from every pool — so `completes_xi` must say
    so even though every outfield line is already covered."""
    my_rows, pool = _gk_less_squad_pool()
    plan = rebuild.build_plan(
        my_rows=my_rows, affordable=pool, cash=50_000_000, floor=0, bench=0
    )
    assert plan.completes_xi is False


# --- build_plan: the cash floor ---------------------------------------------


def test_the_cash_floor_is_kept_when_the_plan_completes_without_it():
    my_rows = _squad(gk=1, d=2, m=6, f=5)  # DEF short by 1
    pool = [_candidate(1, DEF, clause=5_000_000, sf=300)]
    floor = 2_000_000
    plan = rebuild.build_plan(
        my_rows=my_rows, affordable=pool, cash=50_000_000, floor=floor, bench=0
    )
    assert plan.completes_xi is True
    assert plan.spends_floor is False
    assert plan.cash_before - plan.total_cost >= floor


def test_completing_the_eleven_wins_over_keeping_the_cash_floor():
    my_rows = _squad(gk=1, d=2, m=6, f=5)  # DEF short by 1
    pool = [_candidate(1, DEF, clause=5_000_000, sf=300)]
    floor = 2_000_000
    plan = rebuild.build_plan(
        my_rows=my_rows, affordable=pool, cash=6_000_000, floor=floor, bench=0
    )
    assert plan.completes_xi is True
    assert plan.spends_floor is True
    assert plan.total_cost == 5_000_000


# --- build_plan: the bench ----------------------------------------------------


def test_a_bench_candidate_below_the_starts_above_bar_is_never_bought_as_cover():
    """A substitute who never plays cannot cover an injury and cannot be
    fielded, so he must never be bought even when he is the only body left
    to buy — `config.LINEUP_SUB_STARTS_ABOVE` is the bar."""
    my_rows = _squad(gk=1, d=3, m=4, f=3)  # exactly 3-4-3: no XI holes at all
    below_bar = _candidate(
        1, DEF, clause=3_000_000, sf=config.LINEUP_SUB_STARTS_ABOVE - 50
    )
    above_bar = _candidate(
        2, DEF, clause=4_000_000, sf=config.LINEUP_SUB_STARTS_ABOVE + 50
    )
    plan = rebuild.build_plan(
        my_rows=my_rows, affordable=[below_bar, above_bar], cash=50_000_000, floor=0
    )
    bought_ids = {s.row["bw_id"] for s in plan.signings}
    assert 1 not in bought_ids
    assert 2 in bought_ids
