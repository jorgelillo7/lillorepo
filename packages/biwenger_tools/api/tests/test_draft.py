"""Tests for the draft state machine: snake ordering, budgets, squad
composition, pick validation/application, name resolution and CSV loading.

All pure — no HTTP, no Firestore, no Telegram. `players` fixtures below only
need the two keys `validate_pick`/`apply_pick` actually read: `price` and
`position` (GK/DEF/MID/FWD, from `lineup.py`).
"""

import pytest

from packages.biwenger_tools.api.logic.draft import (
    BUDGET_OVERRIDES,
    DraftError,
    DraftState,
    NUM_ROUNDS,
    Pick,
    apply_pick,
    build_budgets,
    composition_ok,
    composition_reachable,
    draft_order_sequence,
    join_market_to_biwenger,
    load_market_csv,
    new_draft_state,
    pick_number_to_slot,
    resolve_order,
    resolve_player_name,
    slot_to_pick_number,
    state_from_dict,
    state_to_dict,
    validate_pick,
    whose_turn,
)
from packages.biwenger_tools.api.logic.draft import DEFAULT_ORDER
from packages.biwenger_tools.api.logic.lineup import DEF, FWD, GK, MID

ORDER = [1, 2, 3, 4, 5, 6, 7]


# --- snake ordering: global pick number <-> (round, position, manager) ----


def test_pick_number_to_slot_round_1_matches_order():
    for i, manager in enumerate(ORDER, start=1):
        assert pick_number_to_slot(i, ORDER) == (1, i, manager)


def test_pick_number_to_slot_round_2_is_reversed():
    for i, manager in enumerate(reversed(ORDER), start=1):
        assert pick_number_to_slot(7 + i, ORDER) == (2, i, manager)


def test_pick_number_to_slot_round_3_follows_order_again():
    for i, manager in enumerate(ORDER, start=1):
        assert pick_number_to_slot(14 + i, ORDER) == (3, i, manager)


def test_pick_number_to_slot_round_boundary_off_by_one():
    """The snake pivots at the round boundary, it doesn't restart: pick 7
    (round 1, last position) and pick 8 (round 2, first position) belong to
    the SAME manager — the classic off-by-one this rule is built around."""
    assert pick_number_to_slot(7, ORDER) == (1, 7, 7)
    assert pick_number_to_slot(8, ORDER) == (2, 1, 7)
    assert pick_number_to_slot(14, ORDER) == (2, 7, 1)
    assert pick_number_to_slot(15, ORDER) == (3, 1, 1)


def test_pick_number_to_slot_rejects_non_positive():
    with pytest.raises(ValueError):
        pick_number_to_slot(0, ORDER)


def test_slot_to_pick_number_is_inverse_of_pick_number_to_slot():
    n = len(ORDER)
    for global_pick in range(1, n * NUM_ROUNDS + 1):
        round_num, position, _ = pick_number_to_slot(global_pick, ORDER)
        assert slot_to_pick_number(round_num, position, n) == global_pick


def test_draft_order_sequence_alternates_direction_each_round():
    seq = draft_order_sequence(ORDER, rounds=3)
    assert seq[0:7] == list(ORDER)
    assert seq[7:14] == list(reversed(ORDER))
    assert seq[14:21] == list(ORDER)


def test_draft_order_sequence_length_matches_managers_times_rounds():
    seq = draft_order_sequence(ORDER)
    assert len(seq) == len(ORDER) * NUM_ROUNDS


# --- resolve_order / default season order ----------------------------------


def test_resolve_order_matches_case_and_accent_insensitively():
    members = {1: "Ruben", 2: "Javi"}
    assert resolve_order(["rubén", "JAVI"], members) == [1, 2]


def test_resolve_order_raises_on_unknown_name():
    with pytest.raises(ValueError):
        resolve_order(["Nobody"], {1: "Ruben"})


def test_resolve_order_raises_on_ambiguous_name():
    with pytest.raises(ValueError):
        resolve_order(["Manu"], {1: "Manu", 2: "Manu"})


def test_default_order_resolves_seven_distinct_managers():
    assert len(DEFAULT_ORDER) == 7
    assert len(set(DEFAULT_ORDER)) == 7


# --- budgets -----------------------------------------------------------


def test_build_budgets_applies_override_on_top_of_base():
    budgets = build_budgets([10, 20, 30], base=50_000_000, overrides={20: 52_000_000})
    assert budgets == {10: 50_000_000, 20: 52_000_000, 30: 50_000_000}


def test_build_budgets_defaults_to_base_with_no_overrides():
    budgets = build_budgets([1, 2], base=50_000_000, overrides={})
    assert budgets == {1: 50_000_000, 2: 50_000_000}


def test_default_budget_overrides_apply_to_exactly_one_manager():
    assert len(BUDGET_OVERRIDES) == 1
    assert list(BUDGET_OVERRIDES.values()) == [52_000_000]


# --- squad composition: valid XI + 1 sub per line ---------------------------


def _counts(gk=0, d=0, m=0, f=0):
    return {GK: gk, DEF: d, MID: m, FWD: f}


def test_composition_ok_true_when_a_formation_and_its_subs_fit():
    # 3-4-3 needs DEF>=4, MID>=5, FWD>=4 (starters+1); this squad clears it.
    assert composition_ok(_counts(gk=2, d=4, m=7, f=4)) is True


def test_composition_ok_false_with_only_one_goalkeeper():
    assert composition_ok(_counts(gk=1, d=4, m=7, f=4)) is False


def test_composition_ok_false_when_every_line_is_too_thin():
    # every formation needs DEF>=3 (min n_def is 3): 2 can never clear it.
    assert composition_ok(_counts(gk=2, d=2, m=2, f=2)) is False


def test_composition_reachable_from_scratch_matches_squad_size():
    """With nothing drafted yet, every formation's minimum (2 GK + 10
    outfield with subs) sums to exactly SQUAD_SIZE — so an empty squad is
    reachable with SQUAD_SIZE more picks, and not with one fewer."""
    assert composition_reachable({}, NUM_ROUNDS) is True
    assert composition_reachable({}, NUM_ROUNDS - 1) is False


def test_composition_reachable_false_with_negative_slots():
    assert composition_reachable(_counts(gk=2, d=5, m=5, f=5), -1) is False


def test_composition_reachable_true_when_already_valid_with_zero_slots_left():
    assert composition_reachable(_counts(gk=2, d=4, m=5, f=4), 0) is True


# --- validate_pick / apply_pick ------------------------------------------


def test_validate_pick_rejects_wrong_turn():
    state = new_draft_state(order=[1, 2])
    players = {101: {"price": 1_000_000, "position": GK}}
    result = validate_pick(state, manager_id=2, player_id=101, players=players)
    assert result.ok is False
    assert result.error is DraftError.NOT_YOUR_TURN
    assert result.message


def test_validate_pick_rejects_unknown_player():
    state = new_draft_state(order=[1, 2])
    result = validate_pick(state, manager_id=1, player_id=9999, players={})
    assert result.ok is False
    assert result.error is DraftError.PLAYER_UNKNOWN


def test_validate_pick_rejects_player_already_taken():
    state = DraftState(
        order=[1, 2],
        budgets={1: 50_000_000, 2: 50_000_000},
        picks=[],
        squads={1: [], 2: [55]},
        spent={1: 0, 2: 0},
    )
    players = {55: {"price": 100, "position": GK}}
    result = validate_pick(state, manager_id=1, player_id=55, players=players)
    assert result.ok is False
    assert result.error is DraftError.PLAYER_ALREADY_TAKEN


def test_validate_pick_rejects_when_squad_already_full():
    state = DraftState(
        order=[1, 2],
        budgets={1: 50_000_000, 2: 50_000_000},
        picks=[],
        squads={1: list(range(1, 16)), 2: []},
        spent={1: 0, 2: 0},
    )
    players = {999: {"price": 100, "position": GK}}
    result = validate_pick(state, manager_id=1, player_id=999, players=players)
    assert result.ok is False
    assert result.error is DraftError.SQUAD_FULL


def test_validate_pick_rejects_insufficient_budget():
    state = new_draft_state(order=[1, 2], budgets={1: 1_000, 2: 1_000})
    players = {1: {"price": 2_000, "position": GK}}
    result = validate_pick(state, manager_id=1, player_id=1, players=players)
    assert result.ok is False
    assert result.error is DraftError.INSUFFICIENT_BUDGET


def test_validate_pick_rejects_budget_infeasible_near_end_of_draft():
    """The pick is affordable on its own, but spending this much would leave
    less than `remaining_slots * cheapest_available_price` — bricking the
    squad one pick before the end. This is the check the rule exists for."""
    state = DraftState(
        order=[1, 2],
        budgets={1: 100_000, 2: 50_000_000},
        picks=[],
        # Manager 1 already has 13 filler players; one more slot after this.
        squads={1: list(range(900, 913)), 2: []},
        spent={1: 99_100, 2: 0},
    )
    players = {
        1: {"price": 900, "position": GK},  # the pick under test
        2: {"price": 200, "position": DEF},  # cheapest remaining alternative
        3: {"price": 500, "position": MID},
    }
    result = validate_pick(state, manager_id=1, player_id=1, players=players)
    assert result.ok is False
    assert result.error is DraftError.BUDGET_INFEASIBLE


def test_validate_pick_accepts_when_budget_feasibility_holds():
    # Manager 1 already holds 2 GK, 4 DEF, 4 MID, 3 FWD (13 players); this
    # pick is a 5th DEF, leaving 1 slot — reachable via formation 5-3-2.
    filler_positions = {
        900: GK,
        901: GK,
        902: DEF,
        903: DEF,
        904: DEF,
        905: DEF,
        906: MID,
        907: MID,
        908: MID,
        909: MID,
        910: FWD,
        911: FWD,
        912: FWD,
    }
    state = DraftState(
        order=[1, 2],
        budgets={1: 100_000, 2: 50_000_000},
        picks=[],
        squads={1: list(filler_positions), 2: []},
        spent={1: 98_900, 2: 0},
    )
    players = {
        pid: {"price": 0, "position": pos} for pid, pos in filler_positions.items()
    }
    players[1] = {"price": 900, "position": DEF}  # the pick under test
    players[2] = {"price": 200, "position": MID}  # cheapest remaining alternative

    result = validate_pick(state, manager_id=1, player_id=1, players=players)
    assert result.ok is True
    assert result.error is None


def test_validate_pick_rejects_composition_infeasible_on_final_slot():
    """Last pick of the draft (0 slots remain after it): the final position
    counts must already clear `composition_ok` on their own."""
    state = DraftState(
        order=[1, 2],
        budgets={1: 50_000_000, 2: 50_000_000},
        picks=[],
        # 14 filler DEF-only players: no formation has DEF>=15, so no amount
        # of GK/MID/FWD in the last slot can complete a valid squad.
        squads={1: list(range(900, 914)), 2: []},
        spent={1: 0, 2: 0},
    )
    players = {pid: {"price": 0, "position": DEF} for pid in range(900, 914)}
    players[999] = {"price": 0, "position": GK}
    result = validate_pick(state, manager_id=1, player_id=999, players=players)
    assert result.ok is False
    assert result.error is DraftError.COMPOSITION_INFEASIBLE


def test_validate_pick_rejects_after_draft_complete():
    order = [1, 2]
    total = len(order) * NUM_ROUNDS
    dummy_picks = [
        Pick(round=1, position=1, global_pick=i, manager_id=1, player_id=i, price=0)
        for i in range(1, total + 1)
    ]
    state = DraftState(
        order=order,
        budgets={1: 0, 2: 0},
        picks=dummy_picks,
        squads={1: [], 2: []},
        spent={1: 0, 2: 0},
    )
    assert whose_turn(state) is None
    result = validate_pick(state, manager_id=1, player_id=1, players={})
    assert result.ok is False
    assert result.error is DraftError.DRAFT_COMPLETE


def test_validate_pick_accepts_first_pick_of_a_fresh_draft():
    state = new_draft_state(order=ORDER)
    players = {
        101: {"price": 5_000_000, "position": GK},
        102: {"price": 100, "position": DEF},
    }
    result = validate_pick(state, manager_id=1, player_id=101, players=players)
    assert result.ok is True
    assert result.error is None


def test_apply_pick_returns_new_state_without_mutating_the_original():
    state = new_draft_state(order=[1, 2])
    players = {
        101: {"price": 1_000_000, "position": GK},
        102: {"price": 100, "position": DEF},
    }
    new_state, result = apply_pick(state, manager_id=1, player_id=101, players=players)

    assert result.ok is True
    assert state.picks == []
    assert state.squads[1] == []
    assert new_state.picks[0] == Pick(
        round=1, position=1, global_pick=1, manager_id=1, player_id=101, price=1_000_000
    )
    assert new_state.squads[1] == [101]
    assert new_state.spent[1] == 1_000_000
    assert whose_turn(new_state) == 2


def test_apply_pick_does_not_mutate_state_on_rejection():
    state = new_draft_state(order=[1, 2])
    players = {101: {"price": 1_000_000, "position": GK}}
    new_state, result = apply_pick(state, manager_id=2, player_id=101, players=players)
    assert result.ok is False
    assert result.error is DraftError.NOT_YOUR_TURN
    assert new_state is state


# --- state serialisation --------------------------------------------------


def test_state_round_trips_through_dict():
    state = new_draft_state(order=[1, 2])
    players = {
        101: {"price": 1_000_000, "position": GK},
        102: {"price": 500_000, "position": DEF},
    }
    state, _ = apply_pick(state, manager_id=1, player_id=101, players=players)
    state, _ = apply_pick(state, manager_id=2, player_id=102, players=players)

    restored = state_from_dict(state_to_dict(state))

    assert restored == state


def test_state_to_dict_uses_string_keys_for_firestore():
    state = new_draft_state(order=[1, 2])
    data = state_to_dict(state)
    assert set(data["budgets"].keys()) == {"1", "2"}
    assert set(data["squads"].keys()) == {"1", "2"}
    assert set(data["spent"].keys()) == {"1", "2"}


# --- free-text player name resolution --------------------------------------

MARKET_ROWS = [
    {
        "team": "Real Madrid",
        "name": "Vinicius Junior",
        "position": FWD,
        "points": 300,
        "price": 40_000_000,
    },
    {
        "team": "Barcelona",
        "name": "Robert Lewandowski",
        "position": FWD,
        "points": 280,
        "price": 30_000_000,
    },
    {
        "team": "Atletico Madrid",
        "name": "Antoine Griezmann",
        "position": FWD,
        "points": 250,
        "price": 20_000_000,
    },
    {
        "team": "Atletico Madrid",
        "name": "Alvaro Morata",
        "position": FWD,
        "points": 200,
        "price": 15_000_000,
    },
]


def test_resolve_player_name_exact_match():
    result = resolve_player_name("Robert Lewandowski", MARKET_ROWS)
    assert result.ok is True
    assert result.row["name"] == "Robert Lewandowski"


def test_resolve_player_name_prefix_shorthand_resolves_uniquely():
    result = resolve_player_name("lewa", MARKET_ROWS)
    assert result.ok is True
    assert result.row["name"] == "Robert Lewandowski"


def test_resolve_player_name_first_name_token_resolves_uniquely():
    result = resolve_player_name("vinicius", MARKET_ROWS)
    assert result.ok is True
    assert result.row["name"] == "Vinicius Junior"


def test_resolve_player_name_matches_shorthand_prefix_of_first_name():
    result = resolve_player_name("vini", MARKET_ROWS)
    assert result.ok is True
    assert result.row["name"] == "Vinicius Junior"


def test_resolve_player_name_ambiguous_team_hint_returns_ranked_candidates():
    result = resolve_player_name("el 9 del atletico", MARKET_ROWS)
    assert result.ok is False
    assert result.row is None
    names = {c["name"] for c in result.candidates}
    assert names == {"Antoine Griezmann", "Alvaro Morata"}


def test_resolve_player_name_no_match_returns_empty_candidates():
    result = resolve_player_name("goalkeeper of neverland", MARKET_ROWS)
    assert result.ok is False
    assert result.candidates == []


# --- frozen-market CSV loading ----------------------------------------------


def _write_csv(tmp_path, content: str):
    path = tmp_path / "market.csv"
    path.write_bytes(("﻿" + content).encode("utf-8"))
    return str(path)


def test_load_market_csv_parses_bom_and_semicolons(tmp_path):
    content = (
        "Equipo;Jugador;Posición;Puntos;Precio;Extra\n"
        "Real Madrid;Vinicius Junior;Delantero;300;40000000;ignored\n"
        "Barcelona;Robert Lewandowski;Delantero;280;30000000;ignored\n"
    )
    rows = load_market_csv(_write_csv(tmp_path, content))

    assert len(rows) == 2
    assert rows[0] == {
        "team": "Real Madrid",
        "name": "Vinicius Junior",
        "position": FWD,
        "points": 300,
        "price": 40_000_000,
    }


def test_load_market_csv_skips_rows_without_a_player_name(tmp_path):
    content = (
        "Equipo;Jugador;Posición;Puntos;Precio\n"
        "Sevilla;;Defensa;0;0\n"
        "Sevilla;Jesus Navas;Defensa;100;1000000\n"
    )
    rows = load_market_csv(_write_csv(tmp_path, content))
    assert len(rows) == 1
    assert rows[0]["name"] == "Jesus Navas"


def test_load_market_csv_defaults_unparseable_numbers_to_zero(tmp_path):
    content = (
        "Equipo;Jugador;Posición;Puntos;Precio\nSevilla;Jesus Navas;Defensa;-;n/a\n"
    )
    rows = load_market_csv(_write_csv(tmp_path, content))
    assert rows[0]["points"] == 0
    assert rows[0]["price"] == 0


# --- CSV row -> Biwenger id join --------------------------------------------


def test_join_market_to_biwenger_matches_by_normalised_name():
    rows = [
        {
            "team": "Real Madrid",
            "name": "Vinícius Júnior",
            "position": FWD,
            "points": 300,
            "price": 40_000_000,
        }
    ]
    biwenger_players = {
        77: {"id": 77, "name": "Vinicius Junior", "position": FWD, "price": 41_000_000}
    }
    matched, unmatched = join_market_to_biwenger(rows, biwenger_players)
    assert unmatched == []
    assert matched[0]["player_id"] == 77


def test_join_market_to_biwenger_reports_unmatched_rows_instead_of_dropping():
    rows = [
        {"team": "X", "name": "Nobody Real", "position": FWD, "points": 0, "price": 0}
    ]
    matched, unmatched = join_market_to_biwenger(rows, {})
    assert matched == []
    assert unmatched == rows


def test_join_market_to_biwenger_reports_ambiguous_names_as_unmatched():
    rows = [
        {"team": "X", "name": "Juan Garcia", "position": MID, "points": 0, "price": 0}
    ]
    biwenger_players = {
        1: {"id": 1, "name": "Juan Garcia", "position": MID, "price": 1},
        2: {"id": 2, "name": "Juan Garcia", "position": MID, "price": 2},
    }
    matched, unmatched = join_market_to_biwenger(rows, biwenger_players)
    assert matched == []
    assert unmatched == rows
