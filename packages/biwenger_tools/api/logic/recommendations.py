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

import time
from typing import Optional

from core.sdk.biwenger import BiwengerClient
from core.sdk.jp import check_api_health, fetch_all_players, get_predict_rate
from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.player_matching import build_jp_index
from packages.biwenger_tools.api.logic.rows import build_squad_rows
from packages.biwenger_tools.api.player_formatting import POSITION_SHORT, SCORE_SF

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


def _euros(n: int | None) -> str:
    """Format an integer as Spanish-style euros: 12.972.212 €.

    `None` and 0 are surfaced explicitly so the user can tell the difference
    between "Biwenger returned 0" and "Biwenger didn't return this field".
    """
    if n is None:
        return "—"
    s = f"{int(n):,}".replace(",", ".")
    return f"{s} €"


def _sf_of(row: dict) -> int:
    jp = row.get("jp_player")
    if not jp:
        return 0
    return get_predict_rate(jp, SCORE_SF) or 0


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
        "sf": _sf_of(row),
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
        grouped[key].sort(key=_sf_of, reverse=True)
        grouped[key] = [_serialise_row(r) for r in grouped[key][:top]]

    return grouped


def _format_telegram_text(payload: dict) -> str:
    """Render the JSON payload as the Telegram message the bot would send."""
    budget = payload["budget"]
    cash = _euros(budget["cash"])
    target = _euros(budget["target"])
    max_bid_value = budget.get("max_bid")
    max_bid_str = _euros(max_bid_value) if max_bid_value else "—"
    margin = _euros(budget["margin"])
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
                f"cláusula {_euros(r['clause'])} · SF {r['sf']}{badge}"
            )
    return "\n".join(lines)


def _gather_rivals(
    biwenger: BiwengerClient,
    biwenger_players: dict,
    jp_index: dict,
) -> list[dict]:
    """Build the rival_rows list, tagged with `owner = manager_name`.

    Skips the logged-in user's own squad. My own squad is fetched separately
    in `run_recommendations` so we can compute Biwenger's max_bid from it.
    """
    managers = biwenger.get_league_users(config.LEAGUE_DATA_URL)
    rivals: list[dict] = []
    for manager_id, manager_name in managers.items():
        if manager_id == biwenger.user_id:
            continue
        squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, manager_id)
        rows = build_squad_rows(squad, biwenger_players, jp_index, include_clause=True)
        for r in rows:
            r["owner"] = manager_name
            rivals.append(r)
        time.sleep(0.3)
    return rivals


def _filter_affordable(candidates: list[dict], my_ids: set, target: int) -> list[dict]:
    """Keep candidates I can actually afford (clause ≤ target) and skip mine."""
    out: list[dict] = []
    for row in candidates:
        if row.get("bw_id") in my_ids:
            continue
        if not row.get("clausulable_now", False):
            continue
        clause = row.get("clause_value") or 0
        if clause <= 0 or clause > target:
            continue
        if _sf_of(row) <= 0:
            continue
        out.append(row)
    return out


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
    check_api_health(
        config.JP_AUTH_TOKEN,
        competition=config.JP_COMPETITION,
        score_type=config.JP_SCORE_TYPE,
    )
    jp_players = fetch_all_players(
        config.JP_AUTH_TOKEN,
        competition=config.JP_COMPETITION,
        score_type=config.JP_SCORE_TYPE,
    )
    jp_index = build_jp_index(jp_players)

    biwenger = BiwengerClient(
        config.BIWENGER_EMAIL,
        config.BIWENGER_PASSWORD,
        config.LOGIN_URL,
        config.ACCOUNT_URL,
        config.LEAGUE_ID,
    )
    biwenger_players = biwenger.get_all_players_data_map(config.ALL_PLAYERS_DATA_URL)

    # Fetch my squad once: needed to compute max_bid AND to mark my players
    # as excluded from the rival pool. We hit /user/{me}?fields=players(*)
    # via the same paginated client method as the rest.
    my_squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
    my_ids = {p.get("id") for p in my_squad if p.get("id") is not None}

    account_state = biwenger.get_account_state(my_squad, biwenger_players)
    cash, max_bid = account_state["cash"], account_state["max_bid"]

    margin_source = "auto" if margin is None else "manual"
    if margin is None:
        margin = compute_dynamic_margin(cash)
    margin = max(0, margin)
    target = cash + margin

    rivals = _gather_rivals(biwenger, biwenger_players, jp_index)
    affordable = _filter_affordable(rivals, my_ids, target)
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

    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        logger.warning("Telegram credentials missing — skipping send.")
        return {"sent": 0, **payload}

    text = _format_telegram_text(payload)
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text=text,
    )
    return {"sent": 1, **payload}
