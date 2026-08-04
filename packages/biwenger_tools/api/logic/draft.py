"""Pure state machine for the Lloros League annual snake draft.

No HTTP, no Firestore, no Telegram — plain data structures (dataclasses,
dicts, lists) so the whole module is trivially unit-testable. Other layers
persist `DraftState` (see `state_to_dict`/`state_from_dict`) and wire the
Telegram/HTTP glue around `validate_pick`/`apply_pick`.

Reglamento anchors this module encodes: 7 managers, 15 rounds, snake order
(reverses every round), exactly 15 players per squad (a valid XI plus one
substitute per line), raw-euro prices frozen to the closed-market export day.
"""

import csv
import io
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

from core.constants import DRAFT_ORDER_NAMES, LEAGUE_MEMBERS
from packages.biwenger_tools.api.logic.lineup import DEF, FORMATIONS, FWD, GK, MID
from packages.biwenger_tools.api.logic.player_matching import normalize_name

NUM_ROUNDS = 15
SQUAD_SIZE = NUM_ROUNDS  # one pick per round per manager

DEFAULT_BUDGET = 50_000_000

# Resolved from `core.constants` so the api and the published rulebook cannot
# disagree about who picks when.
SEASON_ORDER_NAMES = DRAFT_ORDER_NAMES


def resolve_order(
    names: Sequence[str], members: Mapping[int, str] = LEAGUE_MEMBERS
) -> list:
    """Resolve manager names to `members` ids, preserving `names` order.

    Matching is accent/case-insensitive (`normalize_name`). Raises
    `ValueError` if a name matches zero or more than one member — a
    misconfigured season order should fail loudly at setup time rather than
    silently draft picks for the wrong manager.
    """
    by_name: dict = {}
    for member_id, member_name in members.items():
        by_name.setdefault(normalize_name(member_name), []).append(member_id)

    resolved = []
    unresolved = []
    for name in names:
        ids = by_name.get(normalize_name(name), [])
        if len(ids) != 1:
            unresolved.append(name)
            continue
        resolved.append(ids[0])
    if unresolved:
        raise ValueError(f"Cannot resolve manager name(s) to a member id: {unresolved}")
    return resolved


DEFAULT_ORDER: list = resolve_order(SEASON_ORDER_NAMES)

# Per-manager override on top of `DEFAULT_BUDGET`. Jorge won the Copa Castolo,
# which carries a +2M draft budget bonus into the following season. Keyed by
# manager, never by draft position: the order is inverse to the standings and
# changes every season, so a positional key would silently hand the bonus to
# whoever happens to pick third.
BUDGET_OVERRIDES: dict = {resolve_order(("Jorge",))[0]: 52_000_000}


def build_budgets(
    manager_ids: Sequence[int],
    base: int = DEFAULT_BUDGET,
    overrides: Mapping[int, int] = BUDGET_OVERRIDES,
) -> dict:
    """Per-manager starting budget: `base` for everyone, `overrides` on top."""
    return {m: overrides.get(m, base) for m in manager_ids}


DEFAULT_BUDGETS: dict = build_budgets(DEFAULT_ORDER)


# ---------------------------------------------------------------------------
# Snake ordering: global pick number <-> (round, position, manager)
# ---------------------------------------------------------------------------


def pick_number_to_slot(global_pick: int, order: Sequence[int]) -> tuple:
    """Global 1-indexed pick number -> `(round, position, manager_id)`.

    `position` is the 1-indexed pick number within the round (always
    ascending in time, regardless of direction). Round order reverses every
    round: round 1 draws manager ids from `order` as given, round 2 from
    `order` reversed, round 3 from `order` again, etc. — so `position` 1 of
    round 2 is the manager who held `position` n (last) in round 1, per the
    reglamento's "round 1 order 1..7, round 2 order 7..1".
    """
    n = len(order)
    if global_pick < 1:
        raise ValueError(f"global_pick must be >= 1, got {global_pick}")

    round_idx = (global_pick - 1) // n
    pos_idx = (global_pick - 1) % n
    order_idx = pos_idx if round_idx % 2 == 0 else n - 1 - pos_idx
    return round_idx + 1, pos_idx + 1, order[order_idx]


def slot_to_pick_number(round_num: int, position: int, num_managers: int) -> int:
    """Inverse of `pick_number_to_slot`: `(round, position)` -> global pick.

    `position` is already direction-agnostic (see `pick_number_to_slot`), so
    no reversal is needed here.
    """
    return (round_num - 1) * num_managers + position


def draft_order_sequence(order: Sequence[int], rounds: int = NUM_ROUNDS) -> list:
    """Manager id for every global pick of the whole draft, in pick order."""
    sequence = []
    for r in range(rounds):
        sequence.extend(order if r % 2 == 0 else list(reversed(order)))
    return sequence


# ---------------------------------------------------------------------------
# Draft state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pick:
    round: int
    position: int
    global_pick: int
    manager_id: int
    player_id: int
    price: int


@dataclass
class DraftState:
    order: list
    budgets: dict
    picks: list = field(default_factory=list)
    squads: dict = field(default_factory=dict)
    spent: dict = field(default_factory=dict)


def new_draft_state(
    order: Sequence[int] = DEFAULT_ORDER,
    budgets: Mapping[int, int] | None = None,
) -> DraftState:
    """Fresh draft state: no picks made, empty squads, zero spend."""
    order = list(order)
    resolved_budgets = dict(budgets) if budgets is not None else build_budgets(order)
    return DraftState(
        order=order,
        budgets=resolved_budgets,
        picks=[],
        squads={m: [] for m in order},
        spent={m: 0 for m in order},
    )


def current_pick_number(state: DraftState) -> int:
    """Global pick number the next pick would occupy (1-indexed)."""
    return len(state.picks) + 1


def whose_turn(state: DraftState) -> int | None:
    """Manager id who should pick next, or `None` if the draft is complete."""
    total = len(state.order) * NUM_ROUNDS
    pick_num = current_pick_number(state)
    if pick_num > total:
        return None
    _, _, manager_id = pick_number_to_slot(pick_num, state.order)
    return manager_id


def state_to_dict(state: DraftState) -> dict:
    """Plain-dict serialisation for Firestore (string keys throughout)."""
    return {
        "order": list(state.order),
        "budgets": {str(m): v for m, v in state.budgets.items()},
        "picks": [
            {
                "round": p.round,
                "position": p.position,
                "global_pick": p.global_pick,
                "manager_id": p.manager_id,
                "player_id": p.player_id,
                "price": p.price,
            }
            for p in state.picks
        ],
        "squads": {str(m): list(v) for m, v in state.squads.items()},
        "spent": {str(m): v for m, v in state.spent.items()},
    }


def state_from_dict(data: Mapping) -> DraftState:
    """Inverse of `state_to_dict`."""
    return DraftState(
        order=list(data["order"]),
        budgets={int(m): v for m, v in data.get("budgets", {}).items()},
        picks=[Pick(**p) for p in data.get("picks", [])],
        squads={int(m): list(v) for m, v in data.get("squads", {}).items()},
        spent={int(m): v for m, v in data.get("spent", {}).items()},
    )


# ---------------------------------------------------------------------------
# Squad composition: the fifteen must be able to field some legal XI
# ---------------------------------------------------------------------------

_LINES = (GK, DEF, MID, FWD)
# Every subset of the four lines, for the min-cut below.
_LINE_SUBSETS = tuple(
    frozenset(line for k, line in enumerate(_LINES) if mask >> k & 1)
    for mask in range(1 << len(_LINES))
)


def eligible_lines(player: Mapping) -> frozenset:
    """Every line this player can be fielded in.

    Biwenger hands 107 of 553 players an `altPositions` list, and ignoring it
    reads a DEL/MED hybrid as a pure forward — which is how a squad of five
    forwards, all of whom could play midfield, was told it had no legal future.
    """
    lines = {player.get("position")}
    lines.update(player.get("altPositions") or ())
    return frozenset(line for line in lines if line in _LINES)


def _shortfall(
    eligibilities: Sequence[frozenset], requirement: Mapping[int, int]
) -> int:
    """How many more players `requirement` still needs, given what is held.

    A multi-position player covers whichever line the formation is short of, so
    a per-line count understates the squad. This is the max-flow answer, read
    off its min cut: choose a set of lines to give up on, pay their requirement
    plus one for every held player who can only play inside that set. Sixteen
    subsets, so enumerating them is exact and instant.
    """
    usable = min(
        sum(requirement[line] for line in subset)
        + sum(1 for e in eligibilities if not e <= subset)
        for subset in _LINE_SUBSETS
    )
    return sum(requirement.values()) - usable


def _requirements():
    """One `{line: needed}` per formation Biwenger accepts. Eleven players, one
    keeper — `4-6-0` is on the list, so a squad with no forward at all is legal."""
    return ({GK: 1, DEF: d, MID: m, FWD: f} for _, d, m, f in FORMATIONS)


def squad_lines(player_ids: Iterable[int], players: Mapping[int, Mapping]) -> list:
    """Eligibility per drafted player, skipping anyone the market cannot place
    (coaches come back as position 5)."""
    out = []
    for pid in player_ids:
        lines = eligible_lines(players.get(pid) or {})
        if lines:
            out.append(lines)
    return out


def composition_reachable(
    eligibilities: Sequence[frozenset], remaining_slots: int
) -> bool:
    """True iff the squad can still field some legal XI within `remaining_slots`.

    Only the eleven are checked. The bench is free: the reglamento asks for a
    fieldable XI, and with twelve formations accepted there is almost always
    one that fits what you already hold — blocking a pick on the shape of the
    *bench* rejected picks that were perfectly legal.
    """
    if remaining_slots < 0:
        return False
    return any(
        _shortfall(eligibilities, requirement) <= remaining_slots
        for requirement in _requirements()
    )


def composition_ok(eligibilities: Sequence[frozenset]) -> bool:
    """True iff these players can field a legal XI right now."""
    return composition_reachable(eligibilities, 0)


# ---------------------------------------------------------------------------
# Pick validation and application
# ---------------------------------------------------------------------------


class DraftError(Enum):
    DRAFT_COMPLETE = "draft_complete"
    NOT_YOUR_TURN = "not_your_turn"
    PLAYER_UNKNOWN = "player_unknown"
    PLAYER_ALREADY_TAKEN = "player_already_taken"
    SQUAD_FULL = "squad_full"
    INSUFFICIENT_BUDGET = "insufficient_budget"
    BUDGET_INFEASIBLE = "budget_infeasible"
    COMPOSITION_INFEASIBLE = "composition_infeasible"


@dataclass(frozen=True)
class PickResult:
    ok: bool
    error: DraftError | None = None
    message: str = ""


def _drafted_player_ids(state: DraftState) -> set:
    return {pid for squad in state.squads.values() for pid in squad}


def validate_pick(
    state: DraftState,
    manager_id: int,
    player_id: int,
    players: Mapping[int, Mapping],
) -> PickResult:
    """Validate a pick attempt without mutating `state`.

    `players` maps player_id -> a dict with at least `price` (raw euros) and
    `position` (GK/DEF/MID/FWD id) for every player relevant to the draft —
    both the one being picked and everyone already drafted, since squad
    composition is recomputed from `players`.
    """
    turn = whose_turn(state)
    if turn is None:
        return PickResult(False, DraftError.DRAFT_COMPLETE, "El draft ya ha terminado.")
    if turn != manager_id:
        manager_name = LEAGUE_MEMBERS.get(turn, str(turn))
        return PickResult(
            False,
            DraftError.NOT_YOUR_TURN,
            f"No es tu turno, le toca a {manager_name}.",
        )

    info = players.get(player_id)
    if info is None:
        return PickResult(
            False,
            DraftError.PLAYER_UNKNOWN,
            "No encuentro a ese jugador en el mercado.",
        )

    if player_id in _drafted_player_ids(state):
        return PickResult(
            False, DraftError.PLAYER_ALREADY_TAKEN, "Ese jugador ya ha sido elegido."
        )

    squad = state.squads.get(manager_id, [])
    if len(squad) >= SQUAD_SIZE:
        return PickResult(
            False, DraftError.SQUAD_FULL, "Tu plantilla ya tiene 15 jugadores."
        )

    price = int(info.get("price") or 0)
    budget_left = state.budgets.get(manager_id, 0) - state.spent.get(manager_id, 0)
    if price > budget_left:
        return PickResult(
            False,
            DraftError.INSUFFICIENT_BUDGET,
            f"No llega el presupuesto: quedan {budget_left:,} EUR y el jugador cuesta "
            f"{price:,} EUR.",
        )

    remaining_slots = SQUAD_SIZE - len(squad) - 1
    if remaining_slots > 0:
        drafted_after = _drafted_player_ids(state) | {player_id}
        available_prices = [
            int(p.get("price") or 0)
            for pid, p in players.items()
            if pid not in drafted_after
        ]
        if not available_prices:
            return PickResult(
                False,
                DraftError.BUDGET_INFEASIBLE,
                "No quedan jugadores disponibles para completar la plantilla.",
            )
        cheapest = min(available_prices)
        if (budget_left - price) < remaining_slots * cheapest:
            return PickResult(
                False,
                DraftError.BUDGET_INFEASIBLE,
                "Esa compra deja el presupuesto demasiado justo: no llegaría para "
                f"los {remaining_slots} fichajes que faltan (mínimo disponible "
                f"{cheapest:,} EUR cada uno).",
            )

    lines_after = squad_lines(squad + [player_id], players)
    if not composition_reachable(lines_after, remaining_slots):
        return PickResult(
            False,
            DraftError.COMPOSITION_INFEASIBLE,
            "Esa compra deja imposible formar un once legal con los huecos "
            f"que te quedan ({remaining_slots}).",
        )

    return PickResult(True, None, "Fichaje válido.")


def apply_pick(
    state: DraftState,
    manager_id: int,
    player_id: int,
    players: Mapping[int, Mapping],
) -> tuple[DraftState, PickResult]:
    """Validate and, if valid, apply the pick.

    Returns `(new_state, result)`. On failure `new_state is state` (no
    mutation, caller keeps working from the original state).
    """
    result = validate_pick(state, manager_id, player_id, players)
    if not result.ok:
        return state, result

    price = int(players[player_id].get("price") or 0)
    pick_num = current_pick_number(state)
    round_num, position, _ = pick_number_to_slot(pick_num, state.order)

    new_pick = Pick(
        round=round_num,
        position=position,
        global_pick=pick_num,
        manager_id=manager_id,
        player_id=player_id,
        price=price,
    )
    new_squads = {m: list(v) for m, v in state.squads.items()}
    new_squads.setdefault(manager_id, []).append(player_id)
    new_spent = dict(state.spent)
    new_spent[manager_id] = new_spent.get(manager_id, 0) + price

    new_state = DraftState(
        order=list(state.order),
        budgets=dict(state.budgets),
        picks=list(state.picks) + [new_pick],
        squads=new_squads,
        spent=new_spent,
    )
    return new_state, result


# ---------------------------------------------------------------------------
# Free-text player name resolution (Telegram shorthand -> CSV row)
# ---------------------------------------------------------------------------

_STOPWORDS = {"el", "la", "los", "las", "de", "del", "un", "una"}
_MAX_CANDIDATES = 8

_EXACT_SCORE = 100
_TOKEN_SCORE = 80
_PREFIX_SCORE = 60
_SUBSTRING_SCORE = 40
_TEAM_HINT_SCORE = 20


def _content_tokens(normalized_query: str) -> list:
    """Query tokens with Spanish stopwords and pure-digit tokens dropped.

    Digits (e.g. a shirt number in "el 9 del atleti") are dropped rather than
    matched: the closed-market CSV carries no squad-number column, so a
    numeric token cannot be resolved to a specific player.
    """
    return [
        t for t in normalized_query.split() if t not in _STOPWORDS and not t.isdigit()
    ]


def _match_candidates(query: str, rows: Sequence[Mapping]) -> list:
    """Rank `rows` by how well each matches free-text `query`.

    Returns `[(score, row), ...]` sorted by score descending. Ladder (best
    score kept per row): exact normalised name, name-token match (surname
    shorthand), name-token prefix (e.g. "lewa" -> "Lewandowski"), substring
    of the full name, and a last-resort team-name hint for queries like
    "el 9 del atleti" that carry no player name at all.
    """
    norm_query = normalize_name(query)
    query_tokens = _content_tokens(norm_query)

    scored = []
    for row in rows:
        norm_name = normalize_name(row.get("name", ""))
        norm_team = normalize_name(row.get("team", ""))
        name_tokens = norm_name.split()

        score = 0
        if norm_query and norm_query == norm_name:
            score = _EXACT_SCORE
        elif norm_query and norm_query in name_tokens:
            score = _TOKEN_SCORE
        elif norm_query and any(t.startswith(norm_query) for t in name_tokens):
            score = _PREFIX_SCORE
        elif norm_query and norm_query in norm_name:
            score = _SUBSTRING_SCORE
        elif query_tokens and any(tok in norm_team for tok in query_tokens):
            score = _TEAM_HINT_SCORE

        if score:
            scored.append((score, row))

    scored.sort(key=lambda sr: sr[0], reverse=True)
    return scored


@dataclass(frozen=True)
class NameMatch:
    ok: bool
    row: Mapping | None = None
    candidates: list = field(default_factory=list)


def resolve_player_name(query: str, rows: Sequence[Mapping]) -> NameMatch:
    """Resolve Telegram shorthand against frozen-market `rows`.

    A single top-ranked row resolves unambiguously (`ok=True`, `row` set). A
    tie at the top score — or no match at all — returns `ok=False` with a
    ranked `candidates` list (capped to `_MAX_CANDIDATES`) for the bot to
    render as disambiguation buttons.
    """
    scored = _match_candidates(query, rows)
    if not scored:
        # Half the market carries a one-word Biwenger name ("Cucho", "Pedri"),
        # so adding a surname the export does not use turns a good query into
        # a dead end. Fall back to the individual words before giving up.
        words = normalize_name(query).split()
        if len(words) > 1:
            seen, merged = set(), []
            for word in words:
                for score, row in _match_candidates(word, rows):
                    key = id(row)
                    if key not in seen:
                        seen.add(key)
                        merged.append((score, row))
            merged.sort(key=lambda sr: sr[0], reverse=True)
            if merged:
                return NameMatch(
                    False, None, [row for _, row in merged[:_MAX_CANDIDATES]]
                )
        return NameMatch(False, None, [])

    top_score = scored[0][0]
    top_matches = [row for score, row in scored if score == top_score]
    if len(top_matches) == 1:
        return NameMatch(True, top_matches[0], top_matches)

    return NameMatch(False, None, [row for _, row in scored[:_MAX_CANDIDATES]])


# ---------------------------------------------------------------------------
# Frozen-market CSV loading and Biwenger-id join
# ---------------------------------------------------------------------------

_POSITION_ES = {
    "Portero": GK,
    "Defensa": DEF,
    "Centrocampista": MID,
    "Delantero": FWD,
}


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_market_csv(text: str) -> list:
    """Parse the frozen closed-market export from its raw text.

    Format: UTF-8 BOM, `;`-delimited, columns
    `Equipo;Jugador;Posición;Puntos;Precio;...` (extra columns ignored).
    """
    rows = []
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=";")
    for r in reader:
        name = (r.get("Jugador") or "").strip()
        if not name:
            continue
        rows.append(
            {
                "team": (r.get("Equipo") or "").strip(),
                "name": name,
                "position": _POSITION_ES.get((r.get("Posición") or "").strip()),
                "points": _safe_int(r.get("Puntos")),
                "price": _safe_int(r.get("Precio")),
            }
        )
    return rows


def load_market_csv(path: str) -> list:
    """Parse the frozen closed-market export from a local file."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return parse_market_csv(fh.read())


def join_market_to_biwenger(
    rows: Sequence[Mapping],
    biwenger_players: Mapping,
    teams: Mapping | None = None,
) -> tuple:
    """Join CSV `rows` to Biwenger player ids by normalised name.

    `biwenger_players` is a `{player_id: player_info}` map as returned by
    `BiwengerClient.get_all_players_data_map`. Matching is exact-normalised
    only — the CSV is itself a Biwenger export, so names should align
    closely, and a fuzzy auto-join risks silently picking the wrong player.

    `teams` is an optional `{team_id: team_name}` map (see
    `BiwengerClient.get_all_teams_map`) used to break ties between namesakes:
    the player database carries only a numeric `teamID`, while the CSV names
    the team, so without it two players sharing a name are both unresolvable.

    Returns `(matched, unmatched)`: `matched` rows gain a `player_id` key;
    a row that stays ambiguous, or matches nothing, is reported in
    `unmatched` instead of being dropped.
    """
    index: dict = {}
    for pid, info in biwenger_players.items():
        norm = normalize_name(info.get("name", ""))
        index.setdefault(norm, []).append(pid)

    team_names = {int(tid): normalize_name(n) for tid, n in (teams or {}).items()}

    matched, unmatched = [], []
    for row in rows:
        ids = index.get(normalize_name(row["name"]), [])
        if len(ids) > 1 and team_names:
            row_team = normalize_name(row.get("team", ""))
            ids = [
                pid
                for pid in ids
                if team_names.get(biwenger_players[pid].get("teamID")) == row_team
            ] or ids
        if len(ids) == 1:
            matched.append({**row, "player_id": ids[0]})
        else:
            unmatched.append(row)
    return matched, unmatched
