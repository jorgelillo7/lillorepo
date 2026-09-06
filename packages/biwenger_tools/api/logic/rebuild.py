"""Planner for `/emergencia`'s rebuild mode — what to buy when a single
clausulazo can no longer restore a legal eleven — plus the Firestore
persistence of the plan a manager approves.

No HTTP, no Telegram — `emergency.py` owns the flow this feeds and is the
only caller of `store`/`load`/`discard`.
"""

import time
import uuid
from dataclasses import dataclass
from typing import Mapping, Sequence

from core.sdk import firestore as fs  # noqa: F401 — re-exported as `rebuild.fs`
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import draft
from packages.biwenger_tools.api.logic.clausulazo_candidates import sf_of
from packages.biwenger_tools.api.logic.lineup import DEF, FORMATIONS, FWD, GK, MID

_LINES = (GK, DEF, MID, FWD)

# The floor every formation needs in each line, i.e. what `_requirements()`
# guarantees regardless of which of the 14 shapes gets picked (GK 1, DEF 3,
# MID 1, FWD 0 — `4-6-0` is legal, so forwards are never mandatory). A hole
# in a line with a floor above zero cannot be dodged by choosing a different
# formation; a FWD hole sometimes can.
_LINE_FLOOR = {
    line: min(requirement[line] for requirement in draft._requirements())
    for line in _LINES
}


def eligibilities(rows: list[dict]) -> list[frozenset]:
    """Each row as the set of lines it can fill (primary + alternates).

    Filtered to the four real lines, mirroring the guard at the end of
    `draft.eligible_lines`: Biwenger reports a coach as position 5, and an
    unfiltered `frozenset({5})` reads to `draft._shortfall`'s min-cut as
    "usable inside any subset of lines", which *understates* the shortfall
    — the trigger this feature fires on would fail open, reporting a legal
    eleven that does not exist. Works off squad-row keys
    (`position_id`/`alt_positions`) rather than calling `eligible_lines`
    itself, which reads the raw Biwenger keys (`position`/`altPositions`).
    """
    return [
        frozenset(
            line
            for line in {row.get("position_id"), *(row.get("alt_positions") or [])}
            if line in _LINES
        )
        for row in rows
    ]


def line_deficit(elig: Sequence[frozenset], requirement: Mapping[int, int]) -> dict:
    """`{line: how many more this formation needs}`.

    Maximum bipartite matching of held players onto the formation's slots
    (four lines, at most a couple of dozen players — augmenting paths are
    exact and instant): each player is a source node of capacity 1, each
    line a sink of capacity `requirement[line]`. The unfilled sink capacity
    per line is the hole.

    Invariant, asserted in the tests: `sum(line_deficit(...).values())`
    equals `draft._shortfall(...)` for the same inputs — both read off the
    max flow of the same network, so the *total* cannot disagree even
    though the per-line split can.

    A player eligible for more than one short line can only close one of
    them, and which one is a documented implementation detail rather than a
    cost decision: this augments players in `elig` order, trying each
    player's lines in `requirement`'s own iteration order, deliberately
    blind to price. Cost-awareness belongs to `build_plan`, which shops
    hole by hole against real candidate prices and can already see which
    line is expensive; keeping this function pure and deterministic is
    worth more than a marginally better attribution made with data it has
    no business needing.
    """
    lines = list(requirement.keys())
    match: list[int | None] = [None] * len(elig)

    def used(line: int) -> int:
        return sum(1 for assigned in match if assigned == line)

    def augment(player: int, visited: set) -> bool:
        for line in lines:
            if line in visited or line not in elig[player]:
                continue
            visited.add(line)
            if used(line) < requirement[line]:
                match[player] = line
                return True
            for other in range(len(elig)):
                if match[other] != line:
                    continue
                match[other] = None
                if augment(other, visited):
                    match[player] = line
                    return True
                match[other] = line
        return False

    for player in range(len(elig)):
        augment(player, set())

    return {line: requirement[line] - used(line) for line in lines}


def value_of(row: dict) -> float:
    """Predicted points per euro of clause. Zero-priced rows are already
    filtered out upstream (`clausulazo_candidates.filter_affordable`)."""
    return sf_of(row) / row["clause_value"]


@dataclass(frozen=True)
class Signing:
    row: dict
    line: int
    reserved: int


@dataclass(frozen=True)
class Plan:
    signings: list
    formation: str
    completes_xi: bool
    spends_floor: bool
    total_cost: int
    cash_before: int


# ---------------------------------------------------------------------------
# Small pure helpers shared by target_formation and build_plan
# ---------------------------------------------------------------------------


def _eligible_for(row: dict, line: int) -> bool:
    return line in {row.get("position_id"), *(row.get("alt_positions") or [])}


def _cheapest_cost(pool: list[dict], line: int, exclude_ids: set) -> int | None:
    """Cheapest clause among `pool` candidates eligible for `line`, skipping
    `exclude_ids`. `None` when nobody eligible is left."""
    costs = [
        row["clause_value"]
        for row in pool
        if row["bw_id"] not in exclude_ids and _eligible_for(row, line)
    ]
    return min(costs) if costs else None


def _label_for(requirement: Mapping[int, int]) -> str:
    for label, d, m, f in FORMATIONS:
        if (requirement.get(DEF), requirement.get(MID), requirement.get(FWD)) == (
            d,
            m,
            f,
        ):
            return label
    raise ValueError(f"requirement does not match any known formation: {requirement}")


# ---------------------------------------------------------------------------
# Choosing the formation to aim at
# ---------------------------------------------------------------------------


def _tie_break_cost(
    elig: Sequence[frozenset], requirement: Mapping[int, int], affordable: list[dict]
) -> float:
    """What this formation would cost to complete, at cheapest-body prices.

    One entry per missing slot, not one per short line: a line short of three
    needs three bodies, and pricing it at its single cheapest candidate made a
    5-2-3 three defenders short look cheaper than a 3-4-3 short of one defender
    and two midfielders — then the plan could not fund the shape it had chosen.

    Uses the same claiming rule as the reservation (`_claim_cheapest`) on
    purpose: a tie-break that prices holes differently from the reserve picks
    formations the reserve cannot pay for. A formation with more holes in a
    line than there are distinct bodies to fill them is unreachable, not free,
    so its cost is infinite.
    """
    holes = _holes_from(line_deficit(elig, requirement))
    total, unfilled = _claim_cheapest(holes, affordable, exclude_ids=set())
    return float("inf") if unfilled else float(total)


def target_formation(
    elig: Sequence[frozenset], affordable: list[dict]
) -> tuple[dict, int]:
    """The requirement that costs the fewest signings, and that count.

    Ties break towards the formation whose deficit sits in the cheapest
    lines: "cheapest" means the summed cost of the single cheapest
    `affordable` candidate per line still short (see `_tie_break_cost`) —
    real clause prices, not a guessed per-line rank, which is why this
    takes the candidate pool as well as the eligibility sets. A 4-6-0 that
    needs three defenders is not the same purchase as a 3-2-5 that needs
    three forwards only when defenders are actually cheaper on the market
    right now; a line nobody affordable can play makes its formation
    unreachable rather than free, so it never wins a tie it cannot pay for.
    """
    best_count: int | None = None
    best_cost: float | None = None
    best_requirement: dict | None = None
    for requirement in draft._requirements():
        count = draft._shortfall(elig, requirement)
        cost = _tie_break_cost(elig, requirement, affordable)
        if best_requirement is None or (count, cost) < (best_count, best_cost):
            best_count, best_cost, best_requirement = count, cost, requirement
    return best_requirement, best_count


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


def _ordered_holes(holes: Mapping[int, int], pool: list[dict]) -> list[int]:
    """The eleven's holes (GK excluded), most-constrained first.

    Primary key: `_LINE_FLOOR` descending — a hole in a line every formation
    needs (GK/DEF/MID) is filled before one a different formation could have
    avoided needing at all (FWD, floor 0). Secondary: fewest eligible
    candidates in `pool` — mirrors `lineup._next_slot`'s most-constrained-
    first heuristic. Tertiary: line id, so the order is fully deterministic.
    """
    expanded = []
    for line in _LINES:
        if line == GK:
            continue
        expanded += [line] * max(0, holes.get(line, 0))

    def eligible_count(line: int) -> int:
        return sum(1 for row in pool if _eligible_for(row, line))

    return sorted(
        expanded, key=lambda line: (-_LINE_FLOOR[line], eligible_count(line), line)
    )


def _holes_from(deficit: Mapping[int, int]) -> list:
    """A deficit map flattened to one entry per missing slot, GK excluded.

    The goalkeeper line is never bought (the league's admin cancels a
    clausulazo against a manager's last one, so nobody is ever short), and its
    deficit is identical across every formation — counting it would only mask
    the real tie-break.
    """
    return [
        line
        for line, count in deficit.items()
        if line != GK and count > 0
        for _ in range(count)
    ]


def _claim_cheapest(holes: list, pool: list[dict], exclude_ids: set) -> tuple[int, int]:
    """`(cost, unfilled)` for filling `holes` with the cheapest distinct bodies.

    Processed scarcest-first (`_LINE_FLOOR` order) so a single multi-position
    player is never counted for two different lines — each hole claims its own
    cheapest still-unclaimed body. `unfilled` is how many holes found nobody
    left, which is what separates "this costs a lot" from "this cannot be done
    at any price".
    """
    counts: dict[int, int] = {}
    for line in holes:
        counts[line] = counts.get(line, 0) + 1

    claimed = set(exclude_ids)
    total = 0
    unfilled = 0
    for line in sorted(counts, key=lambda line: (-_LINE_FLOOR[line], line)):
        for _ in range(counts[line]):
            candidates = sorted(
                (
                    row
                    for row in pool
                    if row["bw_id"] not in claimed and _eligible_for(row, line)
                ),
                key=lambda row: row["clause_value"],
            )
            if not candidates:
                unfilled += 1
                continue
            cheapest = candidates[0]
            total += cheapest["clause_value"]
            claimed.add(cheapest["bw_id"])
    return total, unfilled


def _reserve_for(lines: list, pool: list[dict], exclude_ids: set) -> int:
    """What must be held back to still fill `lines` later.

    A hole nobody is left to claim reserves nothing: money cannot hold a place
    for a player who does not exist, and that hole failing is reported at
    commit time rather than here.
    """
    return _claim_cheapest(lines, pool, exclude_ids)[0]


def _attempt_fill(
    holes: list[int], pool: list[dict], budget: int
) -> tuple[list[Signing], int]:
    """One pass over `holes` in order, reserving every later hole's cheapest
    candidate before spending on the current one. A hole with nothing
    affordable within what is left simply stays open — it is not retried."""
    used_ids: set = set()
    signings: list[Signing] = []
    spent = 0
    for i, line in enumerate(holes):
        reserved_for_others = _reserve_for(holes[i + 1 :], pool, used_ids)
        reserved_for_this = _cheapest_cost(pool, line, used_ids) or 0
        spendable = budget - spent - reserved_for_others
        candidates = [
            row
            for row in pool
            if row["bw_id"] not in used_ids
            and _eligible_for(row, line)
            and row["clause_value"] <= spendable
        ]
        if not candidates:
            continue
        winner = max(candidates, key=value_of)
        signings.append(Signing(row=winner, line=line, reserved=reserved_for_this))
        used_ids.add(winner["bw_id"])
        spent += winner["clause_value"]
    return signings, spent


def _fill_xi(
    holes: list[int], pool: list[dict], cash: int, floor: int
) -> tuple[list[Signing], int, bool]:
    """Fill `holes` respecting `floor` first; retry with the full `cash` only
    if that left a hole unfilled — completing the eleven outranks keeping
    the floor, never the other way round (`config.EMERGENCY_CASH_FLOOR`).

    Returns `(signings, spent, spends_floor)`.
    """
    signings, spent = _attempt_fill(holes, pool, cash - floor)
    if floor > 0 and len(signings) < len(holes):
        floor_signings, floor_spent = _attempt_fill(holes, pool, cash)
        if len(floor_signings) > len(signings):
            return floor_signings, floor_spent, floor_spent > (cash - floor)
    return signings, spent, False


def _fill_bench(
    requirement: Mapping[int, int],
    pool: list[dict],
    used_ids: set,
    budget: int,
    bench: int,
    bench_bar: int,
) -> tuple[list[Signing], int]:
    """Up to `bench` extra signings, best value first, restricted to the
    lines the target formation actually uses and to candidates whose
    projection clears `bench_bar` — a substitute nobody expects to play
    cannot cover an injury and cannot be fielded, so he is not cover at any
    price (`config.LINEUP_SUB_STARTS_ABOVE`). Never dips into the cash
    floor: unlike the eleven, a missed bench slot still leaves a legal
    squad.
    """
    lines_used = [
        line for line in _LINES if line != GK and requirement.get(line, 0) > 0
    ]
    used_ids = set(used_ids)
    signings: list[Signing] = []
    spent = 0
    for _ in range(bench):
        spendable = budget - spent
        candidates = [
            row
            for row in pool
            if row["bw_id"] not in used_ids
            and any(_eligible_for(row, line) for line in lines_used)
            and sf_of(row) > bench_bar
            and row["clause_value"] <= spendable
        ]
        if not candidates:
            break
        winner = max(candidates, key=value_of)
        line = next(line for line in lines_used if _eligible_for(winner, line))
        signings.append(Signing(row=winner, line=line, reserved=winner["clause_value"]))
        used_ids.add(winner["bw_id"])
        spent += winner["clause_value"]
    return signings, spent


def build_plan(
    *,
    my_rows: list[dict],
    affordable: list[dict],
    cash: int,
    floor: int = config.EMERGENCY_CASH_FLOOR,
    bench: int = 2,
    bench_bar: int = config.LINEUP_SUB_STARTS_ABOVE,
) -> Plan:
    """Fill the holes that block every formation first, reserving the rest.

    For each hole, in scarcity order (`_ordered_holes`):
      1. reserve `sum(cheapest candidate per remaining hole)` (`_reserve_for`)
      2. spendable = cash - spent - reserved (floor subtracted first, added
         back only if the eleven cannot be completed without it)
      3. among candidates for this line priced <= spendable, take the best
         points per euro (`value_of`)
      4. commit, move to the next hole

    The eleven's holes come first. The `bench` extra signings are then
    chosen the same way but only from candidates whose projection clears
    `bench_bar`, and never by dipping into the floor.

    Goalkeepers are excluded from every pool: `line != GK` throughout — a
    squad short a keeper is a hole this planner never buys its way out of,
    which is exactly why `completes_xi` can be `False` even when every
    other line is fully covered.
    """
    pool = [row for row in affordable if row.get("position_id") != GK]
    elig = eligibilities(my_rows)
    requirement, _ = target_formation(elig, pool)
    holes = line_deficit(elig, requirement)

    xi_holes = _ordered_holes(holes, pool)
    xi_signings, xi_spent, spends_floor = _fill_xi(xi_holes, pool, cash, floor)
    completes_xi = holes.get(GK, 0) == 0 and len(xi_signings) == len(xi_holes)

    used_ids = {s.row["bw_id"] for s in xi_signings}
    bench_signings, bench_spent = _fill_bench(
        requirement, pool, used_ids, cash - xi_spent, bench, bench_bar
    )

    return Plan(
        signings=xi_signings + bench_signings,
        formation=_label_for(requirement),
        completes_xi=completes_xi,
        spends_floor=spends_floor,
        total_cost=xi_spent + bench_spent,
        cash_before=cash,
    )


# ---------------------------------------------------------------------------
# Storage — emergencia/{season}/planes/{plan_id}, thin and season-scoped (D3)
# ---------------------------------------------------------------------------


def _plans_path(season: str) -> str:
    return f"emergencia/{season}/planes"


def store(plan: Plan) -> str:
    """Persist `plan` thinly and return the new document's id.

    Keeps only what `execute_rebuild` needs to re-resolve and re-verify each
    signing later: `bw_id`, `owner_user_id`, `line`, `reserved`,
    `clause_at_plan`. Never `jp_player` — a candidate row carries the whole
    provider payload, and this document is read exactly once, by the
    manager's own confirmation tap. Names are re-resolved at execution from
    the players map, the way `execute_clausulazo` already does for its
    success message.
    """
    plan_id = uuid.uuid4().hex
    doc = {
        "formation": plan.formation,
        "cash_before": plan.cash_before,
        "created_at": time.time(),
        "signings": [
            {
                "bw_id": signing.row["bw_id"],
                "owner_user_id": signing.row["owner_user_id"],
                "line": signing.line,
                "reserved": signing.reserved,
                "clause_at_plan": signing.row["clause_value"],
            }
            for signing in plan.signings
        ],
    }
    fs.set_document(_plans_path(config.CURRENT_SEASON), plan_id, doc)
    return plan_id


def load(plan_id: str) -> dict | None:
    """The stored plan document, or `None` if it never existed or already ran."""
    return fs.get_document(_plans_path(config.CURRENT_SEASON), plan_id)


def discard(plan_id: str) -> None:
    """Delete the stored plan so `plan_id` can never execute twice."""
    fs.delete_document(_plans_path(config.CURRENT_SEASON), plan_id)
