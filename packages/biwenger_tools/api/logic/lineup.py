"""Lineup optimization for /alinear command.

Given a squad of rows (with jp_player and position data), finds the formation
and 11-player assignment that maximises the total SF predict score.

For a high-level walkthrough of the algorithm (with the multi-position
example that motivated exhaustive backtracking), see the
"How `/alinear` picks the lineup" section of `../README.md`.
"""

from html import escape

from core.sdk.jp import get_predict_rate
from packages.biwenger_tools.api.player_formatting import SCORE_SF

# All supported formations as (label, def, mid, fwd). GK is always 1.
FORMATIONS = [
    ("3-4-3", 3, 4, 3),
    ("3-5-2", 3, 5, 2),
    ("4-3-3", 4, 3, 3),
    ("4-4-2", 4, 4, 2),
    ("4-5-1", 4, 5, 1),
    ("5-3-2", 5, 3, 2),
    ("5-4-1", 5, 4, 1),
    ("3-6-1", 3, 6, 1),
    ("3-3-4", 3, 3, 4),
    ("4-2-4", 4, 2, 4),
    ("4-6-0", 4, 6, 0),
    ("5-2-3", 5, 2, 3),
]

# Position IDs as Biwenger reports them.
GK, DEF, MID, FWD = 1, 2, 3, 4

# Biwenger refuses (HTTP 403, "Captain over max MV") any captain whose
# per-league live market value is ≥ 3M. Rows fed into the picker carry the
# live MV (see `build_squad_rows`, which pulls `owner.price` from the
# user's squad endpoint), so the cap can be applied exactly — no margin.
_CAPTAIN_MAX_PRICE = 3_000_000

# Score we attribute to a player JP has explicitly marked as not in the lineup.
# Big enough to keep the picker honest (positive, so it still beats an empty
# slot), small enough that any other eligible player wins on SF. The user
# prefers filling the slot with someone unlikely to play (0 points) over
# leaving a hole and losing the -4 "empty slot" penalty Biwenger applies.
_UNCALLED_SF = 1


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def pick_lineup(squad_rows: list) -> dict | None:
    """Pick the best (formation, starters, reserves, captain) for the squad.

    Returns `None` if no valid lineup can be formed from the available
    players (e.g. nobody can play GK).

    Return shape::

        {
            "formation": "4-5-1",
            "starters": [(row, pos_id), ...],   # 11 entries
            "reserves": [row | None, ...],       # 4 entries (None = empty slot)
            "captain": row,
            "total_sf": int,
        }
    """
    available = [r for r in squad_rows if _is_available(r)]
    available.sort(key=_sf, reverse=True)

    best: dict | None = None
    # Lexicographic (sum_sf, back_bias). Same tiebreaker as `_try_fill`, so
    # ties between formations (3-4-3 vs 4-4-2 with the same SF) are broken in
    # favour of the one that places more players further back than their
    # primary position.
    best_score: tuple[int, int] = (-1, -(10**9))

    for label, n_def, n_mid, n_fwd in FORMATIONS:
        slots = {GK: 1, DEF: n_def, MID: n_mid, FWD: n_fwd}
        assignment = _try_fill(available, slots)
        if assignment is None:
            continue

        total_sf = sum(_sf(r) for r, _ in assignment)
        total_bias = _back_bias(assignment)
        score = (total_sf, total_bias)
        if score <= best_score:
            continue

        starter_ids = {r["bw_id"] for r, _ in assignment}
        reserves = _pick_reserves(available, starter_ids)
        captain = _pick_captain([r for r, _ in assignment])

        best_score = score
        best = {
            "formation": label,
            "starters": assignment,
            "reserves": reserves,
            "captain": captain,
            "total_sf": total_sf,
        }

    return best


def format_lineup_message(result: dict) -> str:
    """Returns an HTML Telegram message confirming the lineup."""
    formation = result["formation"]
    starters = result["starters"]
    reserves = result["reserves"]
    captain = result.get("captain")
    captain_bw_id = captain["bw_id"] if captain else None
    total_sf = result["total_sf"]

    pos_name = {GK: "POR", DEF: "DEF", MID: "MED", FWD: "DEL"}
    lines = [f"<b>✅ Alineación aplicada — {formation}</b> (SF total: {total_sf})\n"]

    for pos_id in (GK, DEF, MID, FWD):
        group = [(r, p) for r, p in starters if p == pos_id]
        group.sort(key=lambda rp: _sf(rp[0]), reverse=True)
        for row, _ in group:
            sf = _sf(row)
            cap = " ©" if captain_bw_id and row["bw_id"] == captain_bw_id else ""
            lines.append(f"{pos_name[pos_id]} {escape(row['name'])} (SF:{sf}){cap}")

    if captain is None:
        lines.append(
            "\n⚠️ <b>Sin capitán</b>: ningún titular cabe bajo el tope de 3M de MV. "
            "Asigna capitán manualmente en la app."
        )

    filled = [(pos_name[pos], r) for pos, r in zip((GK, DEF, MID, FWD), reserves) if r]
    if filled:
        lines.append("\n<b>Suplentes:</b>")
        for label, r in filled:
            lines.append(f"  {label} {escape(r['name'])} (SF:{_sf(r)})")

    uncalled = [r for r, _ in starters if _is_uncalled(r)]
    if uncalled:
        lines.append("\n<b>⚠️ Aviso — alineados sin estar convocados</b>")
        lines.append("  (mejor 0 puntos que dejar hueco y perder -4):")
        for r in uncalled:
            lines.append(f"  · {escape(r['name'])}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers — tiny pure functions used throughout
# ---------------------------------------------------------------------------


def _sf(row: dict) -> int:
    """Predicted SF score for a player.

    Special cases:
    - 0 if JP has no prediction at all.
    - `_UNCALLED_SF` (1) if JP has marked the player as `playerInLineup=False`
      ("no convocado"). They stay eligible so the picker doesn't leave a slot
      empty (Biwenger penalises an empty slot by -4), but they only get used
      when there is no real alternative — any other available player at the
      same position wins easily on SF.
    """
    jp = row.get("jp_player") or {}
    next_match = jp.get("nextMatch") or {}
    if next_match.get("playerInLineup") is False:
        return _UNCALLED_SF
    return get_predict_rate(jp, SCORE_SF) or 0


def _is_uncalled(row: dict) -> bool:
    """True if JP has explicitly flagged the player as not in the lineup."""
    jp = row.get("jp_player") or {}
    next_match = jp.get("nextMatch") or {}
    return next_match.get("playerInLineup") is False


def _positions(row: dict) -> set:
    """All positions a player can cover — primary + any alts."""
    primary = row.get("position_id")
    alts = row.get("alt_positions") or []
    return {primary} | set(alts)


def _back_bias_one(player: dict, slot: int) -> int:
    """Score how "back" a player ends up vs their primary position.

    Biwenger gives a bigger goal-scoring bonus the further back the slot:
    POR +10, DEF +7, MED +5, DEL +4. JP's SF is a single per-player number
    that does NOT model the slot bonus, so when two assignments tie on SF
    we still prefer the one that places more players further back than
    their natural position.

    Returns +1 if the slot is strictly behind the player's primary
    (e.g. a FWD/MID played as MID), 0 if exactly the primary, -1 if the
    slot is ahead of the primary.

    Position IDs increase as you move forward: GK=1 < DEF=2 < MID=3 < FWD=4.
    """
    primary = player.get("position_id")
    if primary is None:
        return 0
    if slot < primary:
        return 1
    if slot > primary:
        return -1
    return 0


def _back_bias(assignment: list) -> int:
    """Sum of `_back_bias_one` across an assignment. Higher = more "back"."""
    return sum(_back_bias_one(p, slot) for p, slot in assignment)


def _is_available(row: dict) -> bool:
    """Whether a player can be picked for the lineup.

    Excludes:
    - players with no JP data (we can't predict their SF),
    - injured or suspended (per JP status),
    - matches in `break` (their team has no game this matchday).

    Note: `playerInLineup is False` ("no convocado") used to be a hard
    exclusion. It is now a soft penalty applied in `_sf` instead — a
    not-called player still beats an empty slot in Biwenger's scoring
    (empty slot = -4, not playing = 0), so we want them as fallback,
    not removed.
    """
    jp = row.get("jp_player")
    if jp is None:
        return False
    if jp.get("status") in ("injured", "suspended"):
        return False
    next_match = jp.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return False
    return True


# ---------------------------------------------------------------------------
# Internal: starters assignment (exhaustive backtracking)
# ---------------------------------------------------------------------------


def _try_fill(players: list, slots: dict) -> list | None:
    """Pick the assignment of `players` to `slots` that maximises (SF, back-bias).

    Memoised exhaustive backtracking: for each open slot try every eligible
    candidate, recurse on the rest, and keep the assignment with the highest
    **lexicographic** `(sum of SF, back-bias)` score. Returns `None` if no
    valid assignment exists.

    Why two metrics:

    1. SF (predicted score) is the primary signal. It already accounts for
       most of what makes a player valuable for a given matchday.
    2. When two assignments tie on SF — which happens often once you have
       multi-position players — Biwenger's per-position goal bonus breaks
       the tie. A DEF that scores a goal earns +7 points, a MID +5, a DEL
       +4. JP's SF is a single number per player and does NOT change with
       the slot, so picking the assignment that places players further back
       captures expected bonus points the SF can't see. See `_back_bias_one`.

    Why memoisation: the naive recursive search explores every ordering of
    player picks, which is up to N! for a single formation. Many of those
    orderings reach the same sub-state `(remaining_players, remaining_slots)`
    by different paths. We cache by that state so each is solved once. A
    squad of 12 with several multi-position players that previously timed
    out the 300s job now completes in under a second.

    Worked example with formation 4-3-3 that motivated the exhaustive search
    (a FWD/MID player X with SF 400, three other FWDs 380/360/340 and three
    MIDs 350/320/280):

      X as FWD → FWDs sum 1140, MIDs sum 950 = 2090
      X as MID → FWDs sum 1080, MIDs sum 1070 = 2150  ← higher SF, picked

    To prune the search a bit, we fill the most-constrained position first
    (fewest eligible players). This does not change correctness but cuts
    branches early.
    """
    if not any(cnt > 0 for cnt in slots.values()):
        return []
    if not players:
        return None

    # We memoise on (frozenset of bw_ids, sorted tuple of (pos, count)).
    # Both keys are hashable and capture exactly the state of the search.
    lookup = {p["bw_id"]: p for p in players}
    cache: dict[tuple, tuple | None] = {}

    def _solve(player_ids: frozenset, slots_t: tuple) -> tuple | None:
        if not slots_t:
            return ()
        key = (player_ids, slots_t)
        if key in cache:
            return cache[key]

        slots_dict = dict(slots_t)

        def eligible(pos: int) -> int:
            return sum(1 for pid in player_ids if pos in _positions(lookup[pid]))

        pos_to_fill = min(slots_dict.keys(), key=eligible)
        new_count = slots_dict[pos_to_fill] - 1
        new_slots = dict(slots_dict)
        if new_count == 0:
            del new_slots[pos_to_fill]
        else:
            new_slots[pos_to_fill] = new_count
        new_slots_t = tuple(sorted(new_slots.items()))

        candidates = sorted(
            (pid for pid in player_ids if pos_to_fill in _positions(lookup[pid])),
            key=lambda pid: _sf(lookup[pid]),
            reverse=True,
        )

        best: tuple | None = None
        best_score = (-1, -(10**9))
        for pid in candidates:
            sub = _solve(player_ids - {pid}, new_slots_t)
            if sub is None:
                continue
            here_sf = _sf(lookup[pid]) + sum(_sf(lookup[s_pid]) for s_pid, _ in sub)
            here_bias = _back_bias_one(lookup[pid], pos_to_fill) + sum(
                _back_bias_one(lookup[s_pid], slot) for s_pid, slot in sub
            )
            score = (here_sf, here_bias)
            if score > best_score:
                best_score = score
                best = ((pid, pos_to_fill),) + sub

        cache[key] = best
        return best

    initial_ids = frozenset(p["bw_id"] for p in players)
    initial_slots = tuple(sorted((p, c) for p, c in slots.items() if c > 0))
    solved = _solve(initial_ids, initial_slots)
    if solved is None:
        return None
    return [(lookup[pid], slot) for pid, slot in solved]


# ---------------------------------------------------------------------------
# Internal: reserves and captain
# ---------------------------------------------------------------------------


def _pick_reserves(available: list, starter_ids: set) -> list:
    """Pick up to 4 reserves in Biwenger's positional order: GK → DEF → MID → FWD.

    For each position slot we pick the highest-SF eligible bench player that
    has not already been picked for an earlier slot. If no candidate exists
    for a slot we leave a `None` there — Biwenger accepts a partial bench.
    """
    bench_pool = [r for r in available if r["bw_id"] not in starter_ids]
    used_ids: set = set()
    reserves: list = []
    for slot_pos in (GK, DEF, MID, FWD):
        candidates = sorted(
            (
                r
                for r in bench_pool
                if r["bw_id"] not in used_ids and slot_pos in _positions(r)
            ),
            key=_sf,
            reverse=True,
        )
        if candidates:
            reserves.append(candidates[0])
            used_ids.add(candidates[0]["bw_id"])
        else:
            reserves.append(None)
    return reserves


def _pick_captain(starters: list) -> dict | None:
    """Pick the highest-SF starter strictly below the 3M MV cap, or `None`.

    Biwenger rejects any captain whose live per-league MV is ≥ 3M. The
    `price` on the row is the live MV (sourced from `owner.price` in the
    squad endpoint, see `build_squad_rows`), so the cap is applied exactly.

    A `price` of 0 means "unknown" and is excluded — gambling a 403 on a
    player whose MV could be anything is worse than returning `None` and
    letting the caller apply the lineup without a captain.
    """
    eligible = [r for r in starters if 0 < r.get("price", 0) < _CAPTAIN_MAX_PRICE]
    if not eligible:
        return None
    return max(eligible, key=_sf)
