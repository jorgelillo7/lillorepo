"""Lineup optimization for /alinear command.

Given a squad of rows (with jp_player and position data), finds the formation
and 11-player assignment that maximises the total SF predict score.

For a high-level walkthrough of the algorithm (with the multi-position
example that motivated exhaustive backtracking), see the
"How `/alinear` picks the lineup" section of `../README.md`.
"""

from html import escape

from core.sdk.jp import get_predict_rate
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import provider_watch
from packages.biwenger_tools.api.player_formatting import CANNOT_PLAY, SCORE_SF

logger = get_logger(__name__)

# Every formation Biwenger's own "Estrategia" picker offers, as
# (label, def, mid, fwd); GK is always 1. All fourteen, transcribed from the
# app — the list was two short (3-2-5 and 5-1-4), so those XIs could never be
# proposed even when a squad's best eleven wanted one. `test_lineup.py` pins
# the set so a future edit cannot quietly drop one again.
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
    ("3-2-5", 3, 2, 5),
    ("5-1-4", 5, 1, 4),
]

# Position IDs as Biwenger reports them.
GK, DEF, MID, FWD = 1, 2, 3, 4

# Display labels for the applied-lineup message and the promotion log.
_POSITION_LABELS = {GK: "POR", DEF: "DEF", MID: "MED", FWD: "DEL"}

# Biwenger refuses (HTTP 403, "Captain over max MV: <X> > 3000000") any
# captain whose cf-base price is ≥ 3M. The check is against the
# competition-level `price` from cf.biwenger.com — NOT the per-league live
# market value (`owner.price`), which can be much lower (Pablo Martínez:
# owner.price 1.6M, cf-base 3.16M; server rejected when we picked him).
# `row["price"]` is the cf-base value, so the cap applies exactly.
_CAPTAIN_MAX_PRICE = 3_000_000

# Score we attribute to a player JP has explicitly marked as not in the lineup.
# What a player scores when JP leaves him out of its projected XI *and* his
# projection does not clear `LINEUP_SUB_STARTS_ABOVE`. Positive, so he still
# beats an empty slot: filling it with someone unlikely to play (0 points)
# beats leaving a hole and taking Biwenger's -4. Above the threshold this does
# not apply — see `_sf`.
_UNCALLED_SF = 1
# Injured, suspended, no fixture or no data. Still ahead of an empty slot.
_DOUBTFUL_SF = 0

# Per-slot branching cap inside `_try_fill`. The exhaustive backtracking
# blows up exponentially when many multi-position players are eligible for
# the same slot (a 20-player squad with several DEF/MID/FWD versatiles
# pushed the search past 30 s and tripped gunicorn). Capping candidates per
# slot to the top-K by SF bounds branching to K^slots while keeping the
# optimal assignment for realistic Biwenger squads: no formation needs more
# than 6 of a single position, and the chance the optimal picks a sub-top-K
# (by SF) player at any given slot is negligible.
_CANDIDATES_PER_SLOT = 4

# Global pool cap per position before `_try_fill`. Trims the search at the
# entry point: only the top-N players by SF eligible for each position make
# it into the candidate pool (multi-position players are kept if they rank
# top-N for any of their positions). N=8 leaves comfortable headroom over
# the max 6 slots any formation uses for one position.
_POOL_PER_POSITION = 8

# The biggest squad the game allows, in this league and every other. Not used
# to reject anything — it is the number the search ceiling below is calibrated
# against, and the reason that ceiling can be a fixed constant rather than a
# guess.
MAX_SQUAD_SIZE = 25

# Hard ceiling on states explored per formation: the last line of defence,
# not a routine limiter.
#
# **The ceiling is really a memory limit.** The cache holds one entry per
# state, so states and bytes are the same number in different units —
# measured at ~321 B per state, i.e. 150k states ≈ 48 MB. The service runs
# 512Mi at concurrency 10, so what a pathological squad costs is not a slow
# request but several holding caches at once, and an OOM kill takes the whole
# container down rather than the one request.
#
# Calibration: across generated `MAX_SQUAD_SIZE` squads, including shapes
# built to be adversarial, the worst single formation reached **42,921**
# states (13 MB, ~3.2 s for the whole solve). The ceiling sits 3.5x above
# that — high enough that an ordinary morning cannot reach it, low enough
# that one formation can never cost more than a tenth of the container.
#
# Note the search does not grow without limit anyway: `_trim_pool_by_position`
# saturates the candidate pool around 17 players, which is why a 25-man squad
# and a 30-man one cost the same. This ceiling exists for the shape that
# defeats that assumption, not for the squads we can predict.
#
# A formation abandoned costs one of fourteen candidate elevens. A container
# killed costs the morning.
_MAX_SEARCH_NODES = 150_000


class _SearchTooWide(Exception):
    """One formation's search blew past `_MAX_SEARCH_NODES`.

    Internal to this module: `_best_eleven` catches it, drops that formation
    and keeps the other thirteen.
    """


class LineupSearchExhausted(Exception):
    """Every formation blew past the ceiling, so there is no eleven to report.

    Deliberately not `None`. `pick_lineup` returns `None` for "this squad
    cannot field a legal eleven", which `/ofertas` reads as "selling him
    leaves you without a team" and turns into a flat refusal. A search we
    abandoned is not that, and must not be mistaken for it — callers that
    treat it as "signal unavailable" get the right answer, and one that lets
    it propagate fails loudly instead of lying.
    """


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
    # Before deciding anything: note whatever the providers sent that this
    # code does not model. Observation only — it changes no pick.
    provider_watch.observe(squad_rows)

    best = _solve(squad_rows)

    # Only a promotion that actually starts is a bet that was placed; one
    # that lost out to a better assignment never reached the pitch.
    if best is not None:
        provider_watch.log_promotions(_promoted_starters(squad_rows, best["starters"]))

    return best


def _solve(squad_rows: list) -> dict | None:
    """The search itself, with none of the observation `pick_lineup` adds."""
    _reset_promotion_cap(squad_rows)

    # The cap is enforced against the line a player is actually ASSIGNED to,
    # which is only known once the XI exists — a promoted defender who covers
    # midfield can land beside the promotion his own line already allowed.
    # So: solve, demote the surplus, solve again. Each pass caps at least one
    # more player and never uncaps, so it terminates in at most one pass per
    # promotion.
    while True:
        best = _best_eleven(squad_rows)
        if best is None or not _demote_surplus_promotions(best["starters"]):
            break
    return best


def xi_snapshot(squad_rows: list) -> dict | None:
    """`{"total_sf": int, "starter_ids": set}` for the best XI these rows can
    field, or `None` if they cannot field one at all.

    The what-if twin of `pick_lineup`, for asking "how much worse is my XI
    without this player" without any of the side effects: `provider_watch`
    logs the promotions that were actually *bet on* every morning, and a
    hypothetical squad that never reaches Biwenger must not write to that
    audit trail. A dozen counterfactual runs per offers inbox would bury the
    one line that records a real decision.

    Returns the starter ids alongside the total because the two answers come
    from one search and belong together: diffing the elevens with and without
    a player names the man who takes his shirt, and it is by construction the
    same man the SF difference is measuring.
    """
    best = _solve(squad_rows)
    if best is None:
        return None
    return {
        "total_sf": best["total_sf"],
        "starter_ids": {row["bw_id"] for row, _ in best["starters"]},
    }


def format_lineup_message(result: dict) -> str:
    """Returns an HTML Telegram message confirming the lineup."""
    formation = result["formation"]
    starters = result["starters"]
    reserves = result["reserves"]
    captain = result.get("captain")
    captain_bw_id = captain["bw_id"] if captain else None
    total_sf = result["total_sf"]

    pos_name = _POSITION_LABELS
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

    # Two different things happened to two different kinds of uncalled player,
    # and one warning for both told the reader the opposite of the truth: a
    # promoted 659 was reported as a hole-filler while the starter he displaced
    # sat on the bench two lines above.
    uncalled = [r for r, _ in starters if _is_uncalled(r)]
    promoted = [r for r in uncalled if _sf(r) > _UNCALLED_SF]
    fillers = [r for r in uncalled if _sf(r) <= _UNCALLED_SF]

    if promoted:
        lines.append("\n<b>💪 Suplentes de JP alineados por proyección</b>")
        lines.append(
            f"  (JP no los pone de titulares, pero proyectan más de "
            f"{config.LINEUP_SUB_STARTS_ABOVE}):"
        )
        for r in promoted:
            lines.append(f"  · {escape(r['name'])} (SF:{_sf(r)})")
    if fillers:
        lines.append("\n<b>⚠️ Aviso — alineados sin estar convocados</b>")
        lines.append("  (mejor 0 puntos que dejar hueco y perder -4):")
        for r in fillers:
            lines.append(f"  · {escape(r['name'])}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers — tiny pure functions used throughout
# ---------------------------------------------------------------------------


def _sf(row: dict) -> int:
    """Predicted SF score for a player.

    A ladder of last resorts rather than a filter, so a slot is only ever left
    empty when the squad genuinely has nobody for it:

    - the real prediction for a player who is expected to play,
    - the projection for a "no convocado" whose rate clears
      `LINEUP_SUB_STARTS_ABOVE`, then `_UNCALLED_SF` (1) below it — or when
      `_apply_promotion_cap` capped him to keep his line's bet singular,
    - `_DOUBTFUL_SF` (0) for injured, sanctioned, no fixture, or no JP data.

    Below the threshold the fallbacks never displace someone who is actually
    going to play. Above it that is exactly what they do, and the point: a
    projection of 659 outranks a certain starter on 228, because JP is
    predicting the XI rather than reporting it.
    """
    jp = row.get("jp_player") or {}
    if jp.get("status") in CANNOT_PLAY:
        return _DOUBTFUL_SF
    next_match = jp.get("nextMatch") or {}
    if next_match.get("status") == "break":
        return _DOUBTFUL_SF
    rate = get_predict_rate(jp, SCORE_SF) or 0
    if next_match.get("playerInLineup") is False:
        if row.get("_promotion_capped"):
            return _UNCALLED_SF
        # JP is predicting the XI, not reporting it. Above the threshold the
        # projection outweighs the prediction: benching a 659 because someone
        # guessed he starts on the bench costs more than starting him and
        # being wrong.
        return rate if rate > config.LINEUP_SUB_STARTS_ABOVE else _UNCALLED_SF
    return rate or _DOUBTFUL_SF


def _is_uncalled(row: dict) -> bool:
    """True if JP has explicitly flagged the player as not in the lineup."""
    jp = row.get("jp_player") or {}
    next_match = jp.get("nextMatch") or {}
    return next_match.get("playerInLineup") is False


def _reset_promotion_cap(squad_rows: list) -> None:
    """Clear every `_promotion_capped` mark before a fresh search.

    `pick_lineup` runs more than once per process on the same reused row
    dicts, and a mark left by a previous call would silently bench a player
    the current squad has every reason to start.
    """
    for row in squad_rows:
        row["_promotion_capped"] = False


def _is_promoted(row: dict) -> bool:
    """True if this row is currently starting-eligible on its projection
    alone, i.e. JP left him out and the threshold lifted him back."""
    return _is_uncalled(row) and _sf(row) > _UNCALLED_SF


def _best_eleven(squad_rows: list) -> dict | None:
    """Best (formation, starters, reserves, captain) at the current marks.

    Raises `LineupSearchExhausted` when every formation hit the node ceiling —
    see that exception for why it is not `None`.
    """
    available = [r for r in squad_rows if _is_available(r)]
    available.sort(key=_sf, reverse=True)
    available = _trim_pool_by_position(available)

    best: dict | None = None
    # Lexicographic (sum_sf, back_bias). Same tiebreaker as `_try_fill`, so
    # ties between formations (3-4-3 vs 4-4-2 with the same SF) are broken in
    # favour of the one that places more players further back than their
    # primary position.
    # Lexicographic (sum_sf, fallback projection, back_bias). The fallback
    # projection outranks the bias deliberately: the bias is worth a point or
    # two of goal bonus, while the gap between two fallbacks is hundreds of
    # projected points. Ranked the other way round, a 197 who gains +1 by
    # dropping back beat a 316 who does not.
    best_score: tuple[int, int, int] = (-1, -1, -(10**9))

    abandoned = 0
    for label, n_def, n_mid, n_fwd in FORMATIONS:
        slots = {GK: 1, DEF: n_def, MID: n_mid, FWD: n_fwd}
        try:
            assignment = _try_fill(available, slots)
        except _SearchTooWide:
            # One formation of fourteen. The others are searched normally, and
            # the eleven that comes back is the best of those — worse than the
            # true optimum only if the optimum lived in the shape we dropped.
            logger.warning(
                "Formation search abandoned at the node ceiling.",
                extra={
                    "formation": label,
                    "squad_size": len(squad_rows),
                    "pool_size": len(available),
                    "ceiling": _MAX_SEARCH_NODES,
                },
            )
            abandoned += 1
            continue
        if assignment is None:
            continue

        total_sf = sum(_sf(r) for r, _ in assignment)
        total_bias = _back_bias(assignment)
        score = (total_sf, _fallback_total(assignment), total_bias)
        if score <= best_score:
            continue

        starter_ids = {r["bw_id"] for r, _ in assignment}
        reserves = _pick_reserves(squad_rows, starter_ids)
        captain = _pick_captain([r for r, _ in assignment])

        best_score = score
        best = {
            "formation": label,
            "starters": assignment,
            "reserves": reserves,
            "captain": captain,
            "total_sf": total_sf,
        }

    if best is None and abandoned == len(FORMATIONS):
        # Nothing was searched to completion, so we know nothing about this
        # squad — which is a different statement from "it cannot field a
        # legal eleven", and must not arrive as the same `None`.
        raise LineupSearchExhausted(
            f"all {abandoned} formations hit the {_MAX_SEARCH_NODES}-state ceiling"
        )
    return best


def _demote_surplus_promotions(starters: list) -> bool:
    """Mark every promotion beyond the first in any assigned line. Returns
    whether anything was marked, i.e. whether the XI must be solved again.

    Biwenger's auto-substitution replaces at most one absent starter per
    line, so the second promotion in a line starts uninsured. The line that
    counts is the one a player is **assigned** to, not his primary: a
    promoted defender who covers midfield spends a midfield bench slot.

    The survivor is the highest projection, ties broken on `bw_id` so the
    same squad always yields the same eleven.
    """
    by_line: dict[int, list[dict]] = {}
    for row, pos_id in starters:
        if _is_promoted(row):
            by_line.setdefault(pos_id, []).append(row)

    demoted = False
    for rows in by_line.values():
        rows.sort(key=lambda r: (-_sf(r), r["bw_id"]))
        for loser in rows[1:]:
            loser["_promotion_capped"] = True
            demoted = True
    return demoted


def _promoted_starters(squad_rows: list, starters: list) -> list[dict]:
    """Build `provider_watch.log_promotions` payloads for the promotions
    that made the XI.

    "Displaced" is the highest-SF certain (`not _is_uncalled`) squad member
    in the promoted player's assigned line who did not start — `None` when
    the line has nobody else to displace. Computed from `squad_rows`, not
    the trimmed candidate pool, so a certain starter dropped before
    `_try_fill` still counts as the insurance that was bypassed.
    """
    starter_ids = {r["bw_id"] for r, _ in starters}
    promotions = []
    for row, pos_id in starters:
        if not _is_promoted(row):
            continue
        certain_in_line = [
            r
            for r in squad_rows
            if r["bw_id"] not in starter_ids
            and r["position_id"] == pos_id
            and not _is_uncalled(r)
        ]
        displaced = max(certain_in_line, key=_sf, default=None)
        promotions.append(
            {
                "player": row.get("name"),
                "projection": _sf(row),
                "threshold": config.LINEUP_SUB_STARTS_ABOVE,
                "position": _POSITION_LABELS.get(pos_id, pos_id),
                "displaced_player": displaced.get("name") if displaced else None,
                "displaced_sf": _sf(displaced) if displaced else None,
            }
        )
    return promotions


def _positions(row: dict) -> set:
    """All positions a player can cover — primary + any alts."""
    primary = row.get("position_id")
    alts = row.get("alt_positions") or []
    return {primary} | set(alts)


# Biwenger's goal bonus by the position a player is FIELDED in. JP's SF is a
# single per-player number that does not model it, so it is what breaks ties
# between assignments that project the same.
GOAL_BONUS = {GK: 10, DEF: 7, MID: 5, FWD: 4}


def _back_bias_one(player: dict, slot: int) -> int:
    """What playing this player out of position is worth, in bonus points.

    The difference between the goal bonus of the slot he fills and of his
    natural one: a FWD played as MID gains +1 (4 → 5), a DEF pushed to MID
    loses -2 (7 → 5), a player in his own position scores 0.

    It used to return only the **direction** — +1 back, -1 forward — which
    made those two look like they cancelled out. They do not: moving one
    player back to make room by moving another forward is usually a loss,
    because the bonus grows faster the further back you go. With magnitudes
    the two candidate elevens of a real squad stopped tying at +1 and split,
    which also removed a tiebreak that had fallen through to the order of
    `FORMATIONS` — a list transcribed from the app, in no meaningful order.

    Deltas, not absolute bonuses: summing the slots' own values would score
    the *formation* rather than the placement, and would always prefer five
    defenders even with nobody out of position.
    """
    primary = player.get("position_id")
    if primary is None or primary not in GOAL_BONUS or slot not in GOAL_BONUS:
        return 0
    return GOAL_BONUS[slot] - GOAL_BONUS[primary]


def _fallback_rate(row: dict) -> int:
    """The projection hiding behind a floored score, used only to rank
    fallbacks against each other.

    `_sf` flattens every uncalled player below the threshold to the same
    `_UNCALLED_SF`, which threw away the fact that one projects 316 and
    another 197. With the scores equal the tie fell to the back-bias, and
    that favoured whichever fallback happened to gain a bonus by dropping
    back — so the cheaper, worse-projected player started and an 11.2M
    substitute sat on the bench.

    Zero for anyone who genuinely cannot play: an injured 400 is not a
    better gamble than an uncalled 200, and ranking him first would field a
    player nobody expects on the pitch.
    """
    jp = row.get("jp_player") or {}
    if jp.get("status") in CANNOT_PLAY:
        return 0
    if (jp.get("nextMatch") or {}).get("status") == "break":
        return 0
    return get_predict_rate(jp, SCORE_SF) or 0


def _fallback_total(assignment: list) -> int:
    """Summed projection of the starters who are only there as fallbacks."""
    return sum(_fallback_rate(r) for r, _ in assignment if _sf(r) <= _UNCALLED_SF)


def _back_bias(assignment: list) -> int:
    """Bonus points gained or lost across an assignment by playing people out
    of position. Higher is better; 0 means nobody was moved."""
    return sum(_back_bias_one(p, slot) for p, slot in assignment)


def _is_available(row: dict) -> bool:
    """Whether a player can be picked for the lineup.

    Nobody is excluded any more. Every reason a player might not play —
    not called up, injured, suspended, no fixture, no JP data at all — is a
    penalty in `_sf` instead, because **an empty slot scores -4 and a player
    who does not play scores 0**. Leaving the slot open is strictly worse than
    filling it with anyone, and fixtures get postponed: a player written off on
    Friday sometimes plays on Tuesday.

    The argument was already made here for "no convocado" and simply never
    extended to the rest. A real alternative always outranks these on SF, so
    they only ever appear when the slot would otherwise stay empty.
    """
    return True


# ---------------------------------------------------------------------------
# Internal: starters assignment (exhaustive backtracking)
# ---------------------------------------------------------------------------


def _trim_pool_by_position(players: list) -> list:
    """Keep each player who ranks in the top-N by SF for any position they
    can play. Drops obviously-unpickable depth (e.g. the 9th DEF when only
    5 are needed) before `_try_fill` so the search space stays bounded for
    20+ player squads. `players` must already be sorted by SF desc.
    """
    keep_ids: set = set()
    for pos in (GK, DEF, MID, FWD):
        seen = 0
        for p in players:
            if pos in _positions(p):
                keep_ids.add(p["bw_id"])
                seen += 1
                if seen >= _POOL_PER_POSITION:
                    break
    return [p for p in players if p["bw_id"] in keep_ids]


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

    lookup = {p["bw_id"]: p for p in players}

    # Everything the search reads about a player, read once.
    #
    # `_sf` was called 2.2M times for a single 25-man solve and `_positions`
    # 2.0M, both pure over a row that does not change while the search runs —
    # together 60% of the time. They are tabled here rather than at
    # `pick_lineup` scope on purpose: `_demote_surplus_promotions` flips
    # `_promotion_capped` between passes and `_sf` reads it, so a table built
    # above that loop would score demoted players with their pre-demotion
    # projection and quietly pick a different eleven.
    sf_by_id = {pid: _sf(row) for pid, row in lookup.items()}
    pos_by_id = {pid: _positions(row) for pid, row in lookup.items()}
    # A starter only there as a fallback contributes his hidden projection to
    # the second tiebreak; everyone else contributes nothing. Same rule as
    # `_fallback_total`, applied per player so it can be accumulated.
    fallback_by_id = {
        pid: (_fallback_rate(row) if sf_by_id[pid] <= _UNCALLED_SF else 0)
        for pid, row in lookup.items()
    }
    bias_by_id_slot = {
        (pid, slot): _back_bias_one(row, slot)
        for pid, row in lookup.items()
        for slot in (GK, DEF, MID, FWD)
    }

    # We memoise on (bitmask of remaining players, sorted tuple of (pos,
    # count)). Both are hashable and capture exactly the state of the search.
    #
    # The mask is an integer, one bit per player in the trimmed pool, and it
    # is where `MAX_SQUAD_SIZE` earns its keep: 25 players is 25 bits, so
    # every subset the search can reach is a small int. The obvious
    # representation — a `frozenset` of ids — measures **728 bytes** at
    # seventeen players against **28** for the int, and with one key per
    # cached state that difference *was* the memory profile: 1260 B per state
    # against roughly 90. Set difference becomes a mask-and, and hashing an
    # int beats hashing a set, so it is faster as well.
    #
    # The value is `(chosen_player, score)` — one id and three ints — and NOT
    # the sub-assignment it belongs to. Storing the whole eleven-long tuple in
    # every entry measured 1370 B per state, so a 25-man squad's worst
    # formation held 55 MB live and a ceiling meant to bound memory would have
    # allowed 200. The assignment is rebuilt afterwards by walking the chosen
    # players back down the states: eleven lookups instead of eleven copies
    # kept in every one of forty thousand entries.
    #
    # The score still rides along so a parent adds one player's contribution
    # rather than re-summing its subtree — that re-summation was 40% of the
    # time before this.
    # Bit i belongs to `players[i]`, which is already sorted by SF descending
    # — so iterating bits low to high walks players best-first, which is the
    # order the candidate sort then relies on to break ties the same way.
    ids_by_bit = [p["bw_id"] for p in players]
    positions_by_bit = [pos_by_id[pid] for pid in ids_by_bit]
    sf_by_bit = [sf_by_id[pid] for pid in ids_by_bit]
    fallback_by_bit = [fallback_by_id[pid] for pid in ids_by_bit]

    def _bits(mask: int):
        """The set bits of `mask`, lowest first (i.e. best SF first)."""
        while mask:
            low = mask & -mask
            yield low.bit_length() - 1
            mask ^= low

    cache: dict[tuple, tuple | None] = {}
    visits = 0

    def _next_slot(mask: int, slots_t: tuple) -> tuple:
        """`(position_to_fill, remaining_slots)` for a state.

        Fills the most-constrained position first — fewest eligible players.
        That does not change which eleven wins, it only prunes earlier; and
        being a pure function of the state is what lets the rebuild below
        recompute it instead of the cache having to remember it.
        """
        slots_dict = dict(slots_t)
        pos_to_fill = min(
            slots_dict.keys(),
            key=lambda pos: sum(1 for b in _bits(mask) if pos in positions_by_bit[b]),
        )
        remaining = dict(slots_dict)
        if remaining[pos_to_fill] == 1:
            del remaining[pos_to_fill]
        else:
            remaining[pos_to_fill] -= 1
        return pos_to_fill, tuple(sorted(remaining.items()))

    def _solve(mask: int, slots_t: tuple) -> tuple | None:
        nonlocal visits
        if not slots_t:
            return None, (0, 0, 0)
        key = (mask, slots_t)
        if key in cache:
            return cache[key]

        visits += 1
        if visits > _MAX_SEARCH_NODES:
            raise _SearchTooWide(f"formation exceeded {_MAX_SEARCH_NODES} states")

        pos_to_fill, new_slots_t = _next_slot(mask, slots_t)

        candidates = sorted(
            (b for b in _bits(mask) if pos_to_fill in positions_by_bit[b]),
            key=lambda b: sf_by_bit[b],
            reverse=True,
        )[:_CANDIDATES_PER_SLOT]

        best: tuple | None = None
        best_score = (-1, -1, -(10**9))
        for bit in candidates:
            sub = _solve(mask & ~(1 << bit), new_slots_t)
            if sub is None:
                continue
            sub_score = sub[1]
            score = (
                sf_by_bit[bit] + sub_score[0],
                fallback_by_bit[bit] + sub_score[1],
                bias_by_id_slot[(ids_by_bit[bit], pos_to_fill)] + sub_score[2],
            )
            if score > best_score:
                best_score = score
                best = (bit, score)

        cache[key] = best
        return best

    initial_mask = (1 << len(ids_by_bit)) - 1
    initial_slots = tuple(sorted((p, c) for p, c in slots.items() if c > 0))
    if _solve(initial_mask, initial_slots) is None:
        return None

    # Walk the winning chain: each state names its player, `_next_slot`
    # recomputes the slot he fills.
    assignment = []
    mask, slots_t = initial_mask, initial_slots
    while slots_t:
        bit = cache[(mask, slots_t)][0]
        pos_to_fill, slots_t = _next_slot(mask, slots_t)
        assignment.append((lookup[ids_by_bit[bit]], pos_to_fill))
        mask &= ~(1 << bit)
    return assignment


# ---------------------------------------------------------------------------
# Internal: reserves and captain
# ---------------------------------------------------------------------------


def _bench_rank(row: dict) -> tuple:
    """How good a substitute is, most important first.

    `_sf` alone left the bench deciding ties by squad order. A doubtful
    forward projecting 63 and a fit one projecting 197 both floor to
    `_UNCALLED_SF`, and the wrong one took the slot — the bench exists for
    the day a starter does not play, so the substitute most likely to be
    worth something is the whole point.

    Versatility breaks what is left: Biwenger's auto-substitution replaces a
    starter with a bench player who covers that position, so a DEL/MED
    reaches two lines where a MED-only reaches one.
    """
    return (_sf(row), _fallback_rate(row), len(_positions(row)))


def _pick_reserves(squad: list, starter_ids: set) -> list:
    """Pick up to 4 reserves in Biwenger's positional order: GK → DEF → MID → FWD.

    Takes the **whole squad**, not the trimmed candidate pool. The trim exists
    to bound the starter search, and letting it reach the bench silently lost
    players: a squad with eleven midfield-eligible names left the midfield
    reserve slot empty because the twelfth-ranked one had been dropped before
    the bench was ever considered.
    """
    bench_pool = [r for r in squad if r["bw_id"] not in starter_ids]
    used_ids: set = set()
    reserves: list = []
    for slot_pos in (GK, DEF, MID, FWD):
        candidates = sorted(
            (
                r
                for r in bench_pool
                if r["bw_id"] not in used_ids and slot_pos in _positions(r)
            ),
            key=_bench_rank,
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

    Biwenger rejects any captain whose cf-base price is ≥ 3M. The `price`
    on the row is the cf-base value (from cf.biwenger.com via
    `build_squad_rows` → `build_row`), so the cap is applied exactly.

    A `price` of 0 means "unknown" and is excluded — gambling a 403 on a
    player whose price could be anything is worse than returning `None` and
    letting the caller apply the lineup without a captain.

    A player JP left out of its projected XI is excluded even when
    `LINEUP_SUB_STARTS_ABOVE` promoted him into the eleven. Starting him is a
    bet with the bench as insurance; captaining him doubles the bet and has
    none. Returning `None` is the better outcome when the only candidates are
    players the provider says are starting on the bench.
    """
    eligible = [
        r
        for r in starters
        if 0 < r.get("price", 0) < _CAPTAIN_MAX_PRICE and not _is_uncalled(r)
    ]
    if not eligible:
        return None
    return max(eligible, key=_sf)


# ---------------------------------------------------------------------------
# Comparing the optimum against what is actually set on Biwenger
# ---------------------------------------------------------------------------


def diff_against_current(result: dict, squad_rows: list, current: dict) -> dict:
    """What changes between the saved lineup and the optimal one, and its cost.

    `current` is `BiwengerClient.get_current_lineup()`. Returns::

        {"comparable", "reason", "identical", "incoming", "outgoing",
         "formation_changed", "captain_changed", "current_sf", "delta"}

    The cost is the honest part. Summing `_sf()` over the saved eleven would
    be wrong: `_sf` reads `_promotion_capped`, which `_solve` flips between
    passes, so a total taken outside the search is not in the same units as
    `result["total_sf"]`. The saved eleven is scored by putting it through the
    solver again — same machine, same state, two numbers that subtract.

    That second solve goes through `xi_snapshot`, never `pick_lineup`: this is
    a counterfactual, and `provider_watch` records the promotions actually bet
    on. A preview must not write to that audit trail.

    `comparable` is False, with a `reason`, when the saved lineup cannot be
    scored — nothing saved, holes in it, a player sold since, or an eleven no
    formation fits. A preview that printed a zero delta for any of those would
    be reporting "no difference" when it means "no idea".
    """
    optimal_ids = {row["bw_id"] for row, _ in result["starters"]}
    saved_ids = set(current.get("player_ids") or ())

    if not saved_ids:
        return _not_comparable("No hay ninguna alineación guardada en Biwenger.")
    if len(saved_ids) < len(optimal_ids):
        return _not_comparable(
            f"Tu alineación tiene {len(saved_ids)} de {len(optimal_ids)} huecos "
            "cubiertos, así que no se puede puntuar."
        )

    by_id = {row["bw_id"]: row for row in squad_rows}
    missing = saved_ids - by_id.keys()
    if missing:
        return _not_comparable(
            "Tu alineación tiene jugadores que ya no están en la plantilla."
        )

    saved = xi_snapshot([by_id[pid] for pid in saved_ids])
    if saved is None:
        return _not_comparable("Tu alineación no encaja en ninguna formación válida.")

    captain = result.get("captain")
    optimal_captain_id = captain["bw_id"] if captain else None
    formation_changed = bool(
        current.get("formation") and current["formation"] != result["formation"]
    )
    captain_changed = current.get("captain_id") != optimal_captain_id

    # The bench is not in `total_sf` — `_pick_reserves` runs after the search
    # and scores nothing. It still decides whether a starter who does not play
    # is covered or leaves the line uncovered, so a difference here is real and
    # the points cannot express it. It gets its own line rather than an
    # invented number folded into the delta.
    saved_bench = {b for b in (current.get("reserve_ids") or []) if b}
    optimal_bench = {r["bw_id"] for r in (result.get("reserves") or []) if r}

    # A player moving between the eleven and the bench is **one** change, and
    # the eleven's line already reports it. Listing the mirror image below
    # reads as a contradiction — "Sale: Rioja" from the eleven and "Entra:
    # Rioja" to the bench are the same man taking the same step. What is left
    # after removing them is bench-only churn, which is the part the eleven
    # cannot tell you about.
    moved = (optimal_ids - saved_ids) | (saved_ids - optimal_ids)
    bench_in = (optimal_bench - saved_bench) - moved
    bench_out = (saved_bench - optimal_bench) - moved

    return {
        "comparable": True,
        "reason": None,
        "identical": (
            saved_ids == optimal_ids
            and saved_bench == optimal_bench
            and not formation_changed
            and not captain_changed
        ),
        "incoming": [by_id[i] for i in optimal_ids - saved_ids if i in by_id],
        "outgoing": [by_id[i] for i in saved_ids - optimal_ids],
        "bench_incoming": [by_id[i] for i in bench_in if i in by_id],
        "bench_outgoing": [by_id[i] for i in bench_out if i in by_id],
        "bench_empty_slots": max(0, len(optimal_bench) - len(saved_bench)),
        "formation_changed": formation_changed,
        "captain_changed": captain_changed,
        "current_formation": current.get("formation"),
        "current_captain_id": current.get("captain_id"),
        "current_sf": saved["total_sf"],
        "delta": result["total_sf"] - saved["total_sf"],
    }


def _not_comparable(reason: str) -> dict:
    return {
        "comparable": False,
        "reason": reason,
        "identical": False,
        "incoming": [],
        "outgoing": [],
        "bench_incoming": [],
        "bench_outgoing": [],
        "bench_empty_slots": 0,
        "formation_changed": False,
        "captain_changed": False,
        "current_formation": None,
        "current_captain_id": None,
        "current_sf": None,
        "delta": None,
    }


def _name_of(rows: list, bw_id) -> str:
    row = next((r for r in rows if r["bw_id"] == bw_id), None)
    return escape(row["name"]) if row else "—"


def format_preview_message(result: dict, diff: dict, squad_rows: list) -> str:
    """The preview, led by the verdict rather than by the eleven.

    `/preview` used to print the optimal lineup and leave the reader to diff
    it against the app by eye. The question it is actually asked is "do I need
    to act", so the answer goes first and the eleven follows for reference.

    Separate from `format_lineup_message`, which confirms a lineup that was
    applied and says so — a preview must never be mistakable for that.
    """
    head = f"<b>👀 Preview — mejor {result['formation']}</b> (SF {result['total_sf']})"

    if not diff.get("comparable"):
        body = [head, "", f"⚠️ {diff['reason']}", "", "La mejor alineación sería:"]
    elif diff["identical"]:
        body = [
            head,
            "",
            "✅ <b>Tu alineación ya es la óptima.</b> Nada que aportar.",
            "",
        ]
    else:
        delta = diff["delta"]
        gain = (
            "mismo once"
            if delta == 0 and not (diff["incoming"] or diff["outgoing"])
            else (
                "cuesta lo mismo — las dos valen igual"
                if delta == 0
                else f"<b>+{delta}</b> si cambias"
            )
        )
        body = [
            head,
            f"Tu alineación: {diff['current_formation'] or '—'} "
            f"(SF {diff['current_sf']}) → {gain}",
            "",
        ]
        for row in sorted(diff["incoming"], key=_sf, reverse=True):
            body.append(f"  🟢 Entra: {escape(row['name'])} (SF {_sf(row)})")
        for row in sorted(diff["outgoing"], key=_sf, reverse=True):
            body.append(f"  🔴 Sale:  {escape(row['name'])} (SF {_sf(row)})")
        if diff["captain_changed"]:
            captain = result.get("captain")
            body.append(
                "  🅒 Capitán: "
                f"{_name_of(squad_rows, diff['current_captain_id'])} → "
                f"{escape(captain['name']) if captain else 'sin capitán'}"
            )
        # Kept apart from the SF line on purpose: the bench is not in
        # `total_sf`, so folding it into the delta would be inventing points.
        # It changes whether an absent starter is covered, which is a
        # different kind of gain and says so.
        if (
            diff["bench_incoming"]
            or diff["bench_outgoing"]
            or diff["bench_empty_slots"]
        ):
            if body[-1] != "":
                body.append("")
            if diff["bench_empty_slots"] and not diff["bench_incoming"]:
                # Every slot you lack is filled by someone dropping out of the
                # eleven, and the line above already named him. Saying "1 hueco"
                # and listing nobody left the reader with a number and no story.
                body.append(
                    f"  🪑 Banquillo: el cambio de arriba cubre "
                    f"{diff['bench_empty_slots']} hueco(s) que tienes vacío(s)"
                )
            elif diff["bench_empty_slots"]:
                body.append(
                    f"  🪑 Banquillo: tienes {diff['bench_empty_slots']} hueco(s) "
                    "sin cubrir — no suma puntos, pero un titular que no juegue "
                    "se queda sin relevo"
                )
            else:
                body.append("  🪑 Banquillo distinto:")
            for row in sorted(diff["bench_incoming"], key=_sf, reverse=True):
                body.append(f"     🟢 {escape(row['name'])} (SF {_sf(row)})")
            for row in sorted(diff["bench_outgoing"], key=_sf, reverse=True):
                body.append(f"     🔴 {escape(row['name'])} (SF {_sf(row)})")
        body.append("")
        body.append("Aplícala con /alinear")
        body.append("")

    lineup = format_lineup_message(result).replace(
        f"<b>✅ Alineación aplicada — {result['formation']}</b> "
        f"(SF total: {result['total_sf']})\n",
        "",
    )
    return "\n".join(body) + lineup
