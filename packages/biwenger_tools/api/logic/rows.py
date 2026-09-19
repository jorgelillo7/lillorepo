"""Row builders shared by every endpoint that renders a squad or market view.

Pure functions over `(biwenger_player_dict, jp_index, oraculo_index)`. Kept
free of side effects so the same row dict feeds the PNG image builder, the JSON
recommendations endpoint, etc.

Three providers meet here. Biwenger owns identity and price, Jornada Perfecta
the base projection, and Oráculo a second opinion — each under its own keys, so
a reader can always tell which of them said what.
"""

import math
import time
from typing import TYPE_CHECKING

from core.sdk.jp import get_predict_rate
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.player_matching import (
    build_jp_index,
    find_player_match,
)
from packages.biwenger_tools.api.player_formatting import SCORE_SF

if TYPE_CHECKING:
    # `custom_prediction` already imports `oraculo_coverage` from this module
    # at load time; importing it back here would make the two initialise
    # each other, so the real import stays function-local (see below) and
    # this one only exists for the type checker.
    from packages.biwenger_tools.api.logic.custom_prediction import ProjectionScale

SECONDS_PER_DAY = 86400


def clausulable_str(locked_until) -> str:
    """Render the `Clausulable` table cell from a `clauseLockedUntil` epoch."""
    if locked_until is None:
        return "Sí"
    remaining_secs = locked_until - time.time()
    if remaining_secs <= 0:
        return "Sí"
    # floor: 11.28 days → 11 (matches "día 21" when today is the 10th)
    # max(1, ...) so sub-day locks still show "No (1d)" instead of "Sí"
    remaining = max(1, math.floor(remaining_secs / SECONDS_PER_DAY))
    return f"No ({remaining}d)"


def clause_str(clause) -> str:
    if not clause:
        return "-"
    m = int(clause) / 1_000_000
    return f"{m:.1f}M" if int(clause) % 1_000_000 else f"{int(m)}M"


def build_oraculo_index(
    entries: list,
    lists: dict | None = None,
    shortlist_entries: list | None = None,
) -> dict:
    """An index over Oráculo rows, matched by the same machinery as JP.

    Oráculo is a **third naming universe** beside Biwenger and JP, so it goes
    through `player_matching` rather than a bespoke comparison — the traps are
    the same ones (accents, mononyms, two players sharing a surname) and they
    are already solved once.

    `lists` maps a list name to the slugs on it, so a row can carry which
    shortlists its player appears on without a second scan per player.

    `shortlist_entries` are the shortlist rows themselves, indexed separately
    so a player can be recognised by name even when no projection carries
    him. Oráculo's projections fill up as the matchday approaches — 67
    players three days out against 497 on the eve — while the shortlists are
    published from the start. Resolving only through the projections left the
    shortlists invisible for most of the week, which is most of the market.
    """
    normalised = [
        {"name": entry.get("playerName"), "slug": entry.get("slug"), "_oraculo": entry}
        for entry in entries or []
        if entry.get("playerName")
    ]
    index = build_jp_index(normalised)
    by_slug: dict[str, list[str]] = {}
    for list_name, slugs in (lists or {}).items():
        for slug in slugs or []:
            by_slug.setdefault(slug, []).append(list_name)
    index["lists_by_slug"] = {slug: sorted(names) for slug, names in by_slug.items()}
    index["shortlist_index"] = build_jp_index(
        [
            {"name": e.get("playerName"), "slug": e.get("slug"), "_oraculo": e}
            for e in shortlist_entries or []
            if e.get("playerName")
        ]
    )
    return index


def oraculo_coverage(rows: list) -> float:
    """Share of rows Oráculo has an opinion on, 0.0 for an empty list.

    What `ORACULO_MIN_COVERAGE` is compared against: below it the blend is
    switched off for the whole read, because a partial blend promotes whoever
    Oráculo happened to look at first.
    """
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.get("oraculo_matched")) / len(rows)


def build_row(
    biwenger_player: dict, jp_index: dict, oraculo_index: dict | None = None
) -> dict:
    name = biwenger_player.get("name", "N/A")
    oraculo = find_player_match(name, oraculo_index or {}) if oraculo_index else None
    entry = (oraculo or {}).get("_oraculo") or {}
    slug = entry.get("slug")
    if slug is None and oraculo_index:
        # No projection for him yet. The shortlists are published earlier, so
        # try those before concluding Oráculo has never heard of him — being
        # on a list is not a number, but it is an answer to a different
        # question and the market path asks that one.
        listed = find_player_match(name, oraculo_index.get("shortlist_index") or {})
        slug = ((listed or {}).get("_oraculo") or {}).get("slug")
    return {
        "bw_id": biwenger_player.get("id"),
        "name": name,
        "position_id": biwenger_player.get("position"),
        "alt_positions": biwenger_player.get("altPositions") or [],
        "price": biwenger_player.get("price", 0),
        "jp_player": find_player_match(name, jp_index),
        # Oráculo, under its own keys and raw. `matched` is False rather than
        # a zero projection: "not carried" and "expected to score nothing" are
        # different states, and only the second should ever move a number. A
        # silent zero for a missing player once took the league ranking down.
        "oraculo_matched": oraculo is not None,
        "oraculo_points": entry.get("predictedPoints") if oraculo else None,
        "oraculo_chance": entry.get("chance") if oraculo else None,
        "oraculo_lists": (oraculo_index or {}).get("lists_by_slug", {}).get(slug, []),
        # Biwenger's own read on the player. No decision uses it — JP is
        # the source of truth — but carrying it lets `provider_watch`
        # notice when the two disagree.
        "bw_status": biwenger_player.get("status"),
        "bw_status_info": biwenger_player.get("statusInfo"),
    }


def enrich_with_custom_prediction(
    rows: list, oraculo_index: dict | None, oraculo_scale: "ProjectionScale | None"
) -> None:
    """Add `custom_prediction` to every row, in place — or add nothing.

    Public because `auto_bid` builds its market candidates outside the two
    builders here and still has to land on the same numbers: it compares
    those candidates against squad rows, so a second blending path would
    price one side differently from the other.

    `oraculo_scale` is a percentile map between two providers, not a
    property of this row-set (see
    `logic/custom_prediction.py::global_scale`); only `should_blend`'s
    coverage check is legitimately per-table, since coverage genuinely asks
    "does Oráculo know these exact players". No `oraculo_index` or no
    `oraculo_scale` means the caller has nothing to blend with — rows come
    out exactly as they do without this step, so every call site that has
    not been threaded yet keeps working unchanged.

    Imports `custom_prediction` locally: that module already imports
    `oraculo_coverage` from here, and a module-level import back would make
    the two initialise each other.
    """
    if not oraculo_index or oraculo_scale is None:
        return
    from packages.biwenger_tools.api.logic import custom_prediction as cp

    blend_on = cp.should_blend(rows, config.ORACULO_MIN_COVERAGE)
    for row in rows:
        jp_sf = get_predict_rate(row.get("jp_player"), SCORE_SF)
        row["custom_prediction"] = (
            cp.custom_prediction(row, jp_sf, oraculo_scale, blend_on=blend_on)
            if jp_sf is not None
            else None
        )


def build_market_rows(
    market_players: list,
    biwenger_players: dict,
    jp_index: dict,
    oraculo_index: dict | None = None,
    oraculo_scale: "ProjectionScale | None" = None,
) -> list:
    rows = []
    for sale in market_players:
        if sale.get("user") is not None:
            continue
        bw_player = biwenger_players.get(sale.get("player", {}).get("id"))
        if not bw_player:
            continue
        rows.append(build_row(bw_player, jp_index, oraculo_index))
    enrich_with_custom_prediction(rows, oraculo_index, oraculo_scale)
    return rows


def build_squad_rows(
    squad: list,
    biwenger_players: dict,
    jp_index: dict,
    oraculo_index: dict | None = None,
    include_clause: bool = False,
    oraculo_scale: "ProjectionScale | None" = None,
) -> list:
    rows = []
    for player_data in squad:
        bw_player = biwenger_players.get(player_data.get("id"))
        if not bw_player:
            continue
        row = build_row(bw_player, jp_index, oraculo_index)
        # `row["price"]` MUST stay as the cf.biwenger.com base price (not
        # `owner.price`). Biwenger's server validates the 3M captain MV cap
        # against cf-base; using owner.price client-side passes then gets
        # rejected with "Captain over max MV". The maxBid math also reads
        # cf-base. `owner.price` is what YOU paid for the player (acquisition
        # price), surfaced as `acq_price` for the /ofertas algorithm.
        owner = player_data.get("owner") or {}
        row["acq_price"] = int(owner.get("price") or 0)
        row["acq_date"] = owner.get("date")
        last_clause = owner.get("lastClause") or {}
        row["acq_from"] = (last_clause.get("user") or {}).get("name")
        if include_clause:
            locked_until = owner.get("clauseLockedUntil")
            clause_raw = owner.get("clause")
            # Formatted strings — consumed by the PNG renderer.
            row["Clausulable"] = clausulable_str(locked_until)
            row["Cláusula"] = clause_str(clause_raw)
            # Raw values — consumed by the JSON recommendations endpoint.
            # Don't show up in PNG output (only "Clausulable"/"Cláusula" are
            # rendered as extra columns there).
            row["clause_value"] = int(clause_raw) if clause_raw else 0
            row["clausulable_now"] = locked_until is None or (
                (locked_until - time.time()) <= 0
            )
        rows.append(row)
    enrich_with_custom_prediction(rows, oraculo_index, oraculo_scale)
    return rows
