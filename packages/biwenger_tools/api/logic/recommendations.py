"""Budget recommendations — `GET /budget/recommendations` (was `/recomendar`).

Computes "if someone clauses one of my players, who should I go after?":

1. Pull my current cash and Biwenger's `maxBid` (which already accounts for
   the rest of my squad's market value).
2. Walk every rival's squad and keep the players whose clause is currently
   activatable AND whose clause amount ≤ `max_bid`.
3. Group by primary position (GK / DEF / MID / FWD), order by SF score
   descending, return the top-N per position.

Multi-position players (DEF/MID, MID/FWD, …) appear once — under their
primary position — with a `multi` list of secondary positions. The bot
formats that as a `[multi: MED]` badge.
"""

from typing import Optional

from core.sdk.telegram import send_telegram_message_or_raise
from core.utils import format_euros, get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.clausulazo_candidates import (
    filter_affordable,
    gather_rivals,
    sf_of,
)
from packages.biwenger_tools.api.logic.orchestration import (
    build_context,
    require_telegram,
)
from packages.biwenger_tools.api.player_formatting import POSITION_SHORT

logger = get_logger(__name__)

DEFAULT_TOP_N = 3

# Dynamic margin coefficients. When the user does not pass `?margin=N`, we
# compute a margin proportional to their cash so a poor balance doesn't get
# overshadowed by huge-clause players, and a rich balance gets a sensible
# (but bounded) stretch. Rounded to nearest 500k for readability.
_MARGIN_PCT = 0.40
_MARGIN_MIN = 2_000_000
_MARGIN_MAX = 10_000_000
_MARGIN_ROUND = 500_000


def compute_dynamic_margin(cash: int) -> int:
    """Margin proportional to cash, clamped and rounded.

    cash=  5M → 2.0M
    cash= 13M → 5.0M (0.40 * 13M = 5.2M → round to 5.0M)
    cash= 20M → 8.0M
    cash= 30M → 10M (capped)
    """
    if cash <= 0:
        return _MARGIN_MIN
    raw = cash * _MARGIN_PCT
    rounded = round(raw / _MARGIN_ROUND) * _MARGIN_ROUND
    return int(max(_MARGIN_MIN, min(rounded, _MARGIN_MAX)))


# Position labels in the JSON response (English) and for the Telegram message
# header (Spanish with emojis, to match the rest of the bot voice).
_POSITION_KEYS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
_POSITION_LABELS_ES = {
    1: "🥅 Porteros",
    2: "🛡️ Defensas",
    3: "🎯 Centrocampistas",
    4: "⚽ Delanteros",
}


def _short_position_es(position_id: int) -> str:
    """Spanish short label (POR/DEF/MED/DEL) for multi-pos badge."""
    return POSITION_SHORT.get(position_id, "?")


def _serialise_row(row: dict) -> dict:
    """Pick the fields the response (and the bot message) actually need."""
    primary = row.get("position_id")
    alts = [a for a in (row.get("alt_positions") or []) if a != primary]
    return {
        "bw_id": row.get("bw_id"),
        "name": row.get("name"),
        "owner": row.get("owner", ""),
        "clause": row.get("clause_value", 0),
        "sf": sf_of(row),
        "multi": [_short_position_es(a) for a in alts],
    }


def _pick_top_per_position(candidates: list[dict], top: int) -> dict[str, list[dict]]:
    """Group candidates by their primary position, sort by SF desc, slice top.

    Multi-position players appear only under their primary (key in
    `_POSITION_KEYS`); the alts list is exposed via the `multi` field so
    nothing is duplicated across position buckets.
    """
    grouped: dict[str, list[dict]] = {k: [] for k in _POSITION_KEYS.values()}
    for row in candidates:
        key = _POSITION_KEYS.get(row.get("position_id"))
        if key is None:
            continue
        grouped[key].append(row)

    for key in grouped:
        grouped[key].sort(key=sf_of, reverse=True)
        grouped[key] = [_serialise_row(r) for r in grouped[key][:top]]

    return grouped


def _format_telegram_text(payload: dict) -> str:
    """Render the JSON payload as the Telegram message the bot would send."""
    budget = payload["budget"]
    cash = format_euros(budget["cash"])
    target = format_euros(budget["target"])
    max_bid_value = budget.get("max_bid")
    max_bid_str = format_euros(max_bid_value) if max_bid_value else "—"
    margin = format_euros(budget["margin"])
    margin_source = budget.get("margin_source", "auto")
    margin_label = "auto" if margin_source == "auto" else "fijo"

    lines = [
        f"💰 <b>Saldo:</b> {cash}",
        f"🎯 <b>Objetivo (saldo + {margin}, {margin_label}):</b> {target}",
        f"ℹ️ <i>Puja máx. Biwenger: {max_bid_str}</i>",
    ]

    for pos_id in (1, 2, 3, 4):
        key = _POSITION_KEYS[pos_id]
        rows = payload["recommendations"].get(key, [])
        lines.append("")
        lines.append(f"<b>{_POSITION_LABELS_ES[pos_id]}</b>")
        if not rows:
            lines.append("  · (sin candidatos en este rango)")
            continue
        for r in rows:
            badge = f"  <i>[multi: {'/'.join(r['multi'])}]</i>" if r["multi"] else ""
            lines.append(
                f"  · {r['name']} ({r['owner']}) — "
                f"cláusula {format_euros(r['clause'])} · SF {r['sf']}{badge}"
            )
    return "\n".join(lines)


def run_recommendations(
    top: int = DEFAULT_TOP_N,
    margin: Optional[int] = None,
) -> dict:
    """Compute the recommendations and send the formatted message to Telegram.

    `margin` is how much over the user's current cash they'd stretch to. The
    filter uses `cash + margin` as the upper bound on clause amounts — NOT
    `max_bid`, which assumes selling 100% of the squad and is too generous
    for "who could I grab right now" planning.

    When `margin` is `None` (the default — what the bot sends), it is
    computed dynamically from cash (`compute_dynamic_margin`). When the
    caller passes an explicit value, that value wins (after clamping
    happens in the route handler).
    """
    ctx = build_context()

    # Fetch my squad once: needed for max_bid AND to mark my players as
    # excluded from the rival pool.
    my_squad = ctx.biwenger.get_manager_squad(
        config.USER_SQUAD_URL, ctx.biwenger.user_id
    )
    my_ids = {p.get("id") for p in my_squad if p.get("id") is not None}

    account_state = ctx.biwenger.get_account_state(my_squad, ctx.biwenger_players)
    cash, max_bid = account_state["cash"], account_state["max_bid"]

    margin_source = "auto" if margin is None else "manual"
    if margin is None:
        margin = compute_dynamic_margin(cash)
    margin = max(0, margin)
    target = cash + margin

    rivals = gather_rivals(ctx.biwenger, ctx.biwenger_players, ctx.jp_index)
    affordable = filter_affordable(rivals, my_ids, target)
    recommendations = _pick_top_per_position(affordable, top)

    payload = {
        "budget": {
            "cash": cash,
            "max_bid": max_bid,
            "margin": margin,
            "margin_source": margin_source,
            "target": target,
        },
        "recommendations": recommendations,
    }
    logger.info(
        "Recommendations computed.",
        extra={
            "cash": cash,
            "max_bid": max_bid,
            "margin": margin,
            "target": target,
            "rivals": len(rivals),
            "affordable": len(affordable),
            "per_position": {k: len(v) for k, v in recommendations.items()},
        },
    )

    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, **payload}
    token, chat_id = telegram

    text = _format_telegram_text(payload)
    send_telegram_message_or_raise(bot_token=token, chat_id=chat_id, text=text)
    return {"sent": 1, **payload}
