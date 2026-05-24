"""Daily aggressive auto-bidding on the Biwenger daily market.

`POST /market/auto-bid` (Cloud Scheduler 09:00 Madrid) drives this. We
look at the rotating computer-owned free agents Biwenger exposes every
morning, attach SofaScore (Automanager) ratings from JP, and place a
bid on each player according to the tier below — best score first,
stopping when cash runs out.

Tiers (over Biwenger's cf-base `price`, NOT `owner.price`). Every
non-skipped bid carries a random 0–`BID_JITTER_MAX` € offset so the
amounts don't look botty:

    SF > 800             → bid = remaining_cash - jitter   (all-in)
    600 < SF ≤ 800       → bid = price + 5_000_000 + jitter (aggressive)
    400 < SF ≤ 600       → bid = price + 2_000_000 + jitter
    300 < SF ≤ 400       → bid = price +   500_000 + jitter (low conviction)
    SF ≤ 300             → skip

Hard rule across every tier: skip the player when the would-be bid
exceeds `remaining_cash` — we never go negative. The all-in tier bids
the full cash regardless of price (a 26M player against 30M cash is
still a ~30M bid, by the user's call).

Idempotency: Cloud Scheduler retries 5xx responses. We log placed bids
to `auto_bid_log/{YYYY-MM-DD}` (one doc per player) and skip anything
in that log before bidding, so a retry of a half-completed run does
not double-bid the players that already went through.
"""

import random
from datetime import datetime, timedelta
from typing import Optional

import requests

from core.constants import MADRID_TZ
from core.sdk import firestore
from core.sdk.biwenger import BiwengerClient
from core.sdk.jp import (
    check_api_health,
    fetch_all_players,
    get_predict_rate,
)
from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.player_matching import (
    build_jp_index,
    find_player_match,
)
from packages.biwenger_tools.api.player_formatting import SCORE_SF

logger = get_logger(__name__)

# Tier thresholds and surcharges. Kept as a module-level table so the
# unit tests can pin every band without reaching into private helpers.
TIER_ALL_IN_MIN = 800
TIER_PLUS_5M_MIN = 600
TIER_PLUS_2M_MIN = 400
TIER_PLUS_500K_MIN = 300
TIER_PLUS_5M_SURCHARGE = 5_000_000
TIER_PLUS_2M_SURCHARGE = 2_000_000
TIER_PLUS_500K_SURCHARGE = 500_000

# Per-bid anti-pattern jitter. A bot that always bids in round euros
# (10.000.000, 10.500.000, …) is a tell — humans dragging the slider
# in the Biwenger UI never land on exact round numbers. Every bid gets
# a random 0–1000 € offset so the trail looks human. The economic
# impact is negligible (≤0.01% of any tier).
BID_JITTER_MAX = 1000

# Firestore path for today's per-player bid log. Cloud Scheduler retries
# on 5xx — looking up the log before bidding makes a retried run a no-op
# on the players that already went through.
AUTO_BID_LOG_PATH = "auto_bid_log"

# Per-bid Firestore TTL. The TTL policy on the `bids` collection-group
# (configured once via `gcloud firestore fields ttls update expires_at
# --collection-group=bids --enable-ttl`) deletes documents when the
# `expires_at` timestamp passes. 90 days is enough to look back on
# "what did the bot try yesterday/last week" without letting the
# collection grow unbounded.
_LOG_TTL_DAYS = 90


def _today_madrid() -> str:
    """`YYYY-MM-DD` in Europe/Madrid — the doc id for today's log."""
    return datetime.now(MADRID_TZ).strftime("%Y-%m-%d")


def _log_collection_path(day: str) -> str:
    """`auto_bid_log/{day}/bids` — odd-segment subcollection for Firestore."""
    return f"{AUTO_BID_LOG_PATH}/{day}/bids"


def _euros(n: int | None) -> str:
    """Spanish-style thousands separator: 12.345.678 €."""
    if n is None:
        return "—"
    s = f"{int(n):,}".replace(",", ".")
    return f"{s} €"


def _jitter() -> int:
    """Random 0–`BID_JITTER_MAX` € offset for a bid. Indirection makes the
    randomness easy to pin from tests with a single `patch.object`."""
    return random.randint(0, BID_JITTER_MAX)


def tier_bid(sf: int, price: int, remaining_cash: int) -> tuple[Optional[int], str]:
    """Return `(target_bid, label)` for a player, or `(None, reason)` to skip.

    `target_bid` may exceed `remaining_cash` — the caller is in charge of
    the affordability check (so the skip reason can be richer than a
    bare None).

    Every tier adds (or, for T1 all-in, subtracts) a random 0-`BID_JITTER_MAX`
    € offset. The economic impact is < 0.01% of any tier but the bid trail
    stops looking like a bot.
    """
    jitter = _jitter()
    if sf > TIER_ALL_IN_MIN:
        # All-in on the cash we have right now. Price is irrelevant — the
        # user accepts paying 30M for a 26M player rather than leaving cash
        # on the table. Jitter SUBTRACTS here (can't bid > cash); the result
        # stays strictly inside [remaining_cash - BID_JITTER_MAX, remaining_cash].
        return max(0, remaining_cash - jitter), f"T1 all-in (SF {sf})"
    if sf > TIER_PLUS_5M_MIN:
        return price + TIER_PLUS_5M_SURCHARGE + jitter, f"T2 precio+5M (SF {sf})"
    if sf > TIER_PLUS_2M_MIN:
        return price + TIER_PLUS_2M_SURCHARGE + jitter, f"T3 precio+2M (SF {sf})"
    if sf > TIER_PLUS_500K_MIN:
        return price + TIER_PLUS_500K_SURCHARGE + jitter, f"T4 precio+500K (SF {sf})"
    return None, f"SF {sf} ≤ {TIER_PLUS_500K_MIN}"


def _build_candidates(
    market_players: list,
    biwenger_players: dict,
    jp_index: dict,
) -> list[dict]:
    """Daily-market players (computer-owned) enriched with SF + price.

    `sale.get("user") is None` is the marker for daily-market entries;
    user listings carry the seller's id and are out of scope. Anything
    we cannot price (no Biwenger lookup) or cannot score (no JP match)
    is dropped here so the tier loop only sees actionable rows.
    """
    candidates: list[dict] = []
    for sale in market_players:
        if sale.get("user") is not None:
            continue
        player_ref = sale.get("player") or {}
        player_id = player_ref.get("id")
        bw_player = biwenger_players.get(player_id)
        if not bw_player:
            continue
        name = bw_player.get("name") or player_ref.get("name") or "?"
        price = int(bw_player.get("price") or 0)
        jp_player = find_player_match(name, jp_index)
        sf = get_predict_rate(jp_player or {}, SCORE_SF) or 0
        candidates.append(
            {"player_id": player_id, "name": name, "price": price, "sf": sf}
        )
    candidates.sort(key=lambda c: c["sf"], reverse=True)
    return candidates


def _already_bid_ids(day: str) -> set[int]:
    """Player ids already in today's Firestore log (Cloud Scheduler retries)."""
    try:
        return {
            int(doc_id)
            for doc_id, _ in firestore.list_documents(_log_collection_path(day))
        }
    except Exception:  # pragma: no cover — defensive: Firestore unreachable
        # If the log read fails we prefer to bid (the worst case is a rare
        # double-bid on a retry) over silently skipping every candidate
        # because the lookup blew up. The error surfaces in the response.
        logger.exception("Failed to read auto-bid log — proceeding without dedup.")
        return set()


def _log_bid(day: str, candidate: dict, bid_amount: int, offer: dict) -> None:
    """Record a successful bid so a retried run won't repeat it."""
    now = datetime.now(MADRID_TZ)
    firestore.set_document(
        _log_collection_path(day),
        str(candidate["player_id"]),
        {
            "player_id": candidate["player_id"],
            "name": candidate["name"],
            "sf": candidate["sf"],
            "price": candidate["price"],
            "bid": bid_amount,
            "offer_id": offer.get("id"),
            "status": offer.get("status"),
            "created_at": now.isoformat(),
            # Firestore TTL field — the policy on the `bids` collection-group
            # deletes the doc once this timestamp is in the past.
            "expires_at": now + timedelta(days=_LOG_TTL_DAYS),
        },
    )


def _format_telegram_text(
    day: str,
    placed: list[dict],
    skipped: list[dict],
    total_bid: int,
    remaining_cash: int,
) -> str:
    """Render the per-run summary message the Telegram chat receives."""
    header_date = datetime.now(MADRID_TZ).strftime("%d/%m %H:%M")
    lines = [f"💸 <b>Pujas automáticas en el mercado — {header_date}</b>", ""]

    for entry in placed:
        lines.append(
            f"✅ Pujado <b>{_euros(entry['bid'])}</b> por "
            f"<b>{entry['name']}</b> ({entry['tier_label']})"
        )

    if skipped:
        for entry in skipped:
            lines.append(f"⏭️ Saltado <b>{entry['name']}</b> ({entry['reason']})")

    if not placed and not skipped:
        lines.append("Sin candidatos en el mercado diario.")

    lines.append("")
    lines.append(
        f"Total pujado: <b>{_euros(total_bid)}</b> · "
        f"Cash restante: <b>{_euros(remaining_cash)}</b>"
    )
    if not placed:
        lines.append(f"<i>Log: auto_bid_log/{day}</i>")
    return "\n".join(lines)


def _maybe_notify(text: str) -> int:
    """Send the summary to Telegram if creds are configured. Returns sent count."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        logger.warning("Telegram credentials missing — skipping send.")
        return 0
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text=text,
    )
    return 1


def run_auto_bid() -> dict:
    """Walk the daily market, place tiered bids, log + notify.

    Returns a summary dict consumed by the route handler. Side effects:
    Biwenger session + N `POST /api/v2/offers`, Firestore writes per
    successful bid, one Telegram message.
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
    market_players = biwenger.get_market_players(config.MARKET_URL)

    candidates = _build_candidates(market_players, biwenger_players, jp_index)

    account_state = biwenger.get_account_state()
    remaining_cash = int(account_state.get("cash") or 0)

    day = _today_madrid()
    already_bid = _already_bid_ids(day)

    placed: list[dict] = []
    skipped: list[dict] = []

    for candidate in candidates:
        if candidate["player_id"] in already_bid:
            skipped.append(
                {
                    "player_id": candidate["player_id"],
                    "name": candidate["name"],
                    "reason": "ya pujado hoy",
                }
            )
            continue

        target_bid, label = tier_bid(
            candidate["sf"], candidate["price"], remaining_cash
        )
        if target_bid is None:
            # Below the SF floor — record as skipped only if it's borderline
            # interesting (price < 30M and SF > 200) to keep the message short.
            if candidate["sf"] > 200:
                skipped.append(
                    {
                        "player_id": candidate["player_id"],
                        "name": candidate["name"],
                        "reason": label,
                    }
                )
            continue
        if target_bid <= 0 or target_bid > remaining_cash:
            skipped.append(
                {
                    "player_id": candidate["player_id"],
                    "name": candidate["name"],
                    "reason": (
                        f"bid {_euros(target_bid)} > cash {_euros(remaining_cash)}"
                    ),
                }
            )
            continue

        try:
            offer = biwenger.place_market_bid(
                player_id=candidate["player_id"], amount=target_bid
            )
        except requests.RequestException as exc:
            logger.warning(
                "Auto-bid request rejected — continuing.",
                extra={
                    "player_id": candidate["player_id"],
                    "player_name": candidate["name"],
                    "bid": target_bid,
                    "error": str(exc),
                },
            )
            skipped.append(
                {
                    "player_id": candidate["player_id"],
                    "name": candidate["name"],
                    "reason": "Biwenger rechazó la puja",
                }
            )
            continue

        placed.append(
            {
                "player_id": candidate["player_id"],
                "name": candidate["name"],
                "sf": candidate["sf"],
                "price": candidate["price"],
                "bid": target_bid,
                "tier_label": label,
                "offer_id": offer.get("id"),
            }
        )
        _log_bid(day, candidate, target_bid, offer)
        remaining_cash -= target_bid

    total_bid = sum(entry["bid"] for entry in placed)
    text = _format_telegram_text(day, placed, skipped, total_bid, remaining_cash)
    sent = _maybe_notify(text)

    logger.info(
        "Auto-bid run finished.",
        extra={
            "day": day,
            "candidates": len(candidates),
            "placed": len(placed),
            "skipped": len(skipped),
            "total_bid": total_bid,
            "remaining_cash": remaining_cash,
        },
    )
    return {
        "sent": sent,
        "day": day,
        "candidates": len(candidates),
        "bid_count": len(placed),
        "skipped_count": len(skipped),
        "total_bid_eur": total_bid,
        "remaining_cash_eur": remaining_cash,
        "bids": placed,
    }
