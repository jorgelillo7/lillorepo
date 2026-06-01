"""Daily aggressive auto-bidding on the Biwenger daily market.

`POST /market/auto-bid` (Cloud Scheduler 09:00 Madrid) drives this. We
look at the rotating computer-owned free agents Biwenger exposes every
morning, attach SofaScore (Automanager) ratings from JP, and place a
bid on each player according to the tier below — best score first,
stopping when cash runs out.

Tiers (over Biwenger's cf-base `price`, NOT `owner.price`). Boundaries
are INCLUSIVE on the lower end (a player at exactly 400 lands in T3,
not T4). Each non-T1 tier uses `min(price × multiplier, price + cap)`:
the multiplier dominates on cheap players (so a 750K T3 doesn't get a
ridiculous +2M surcharge), the absolute cap dominates on expensive
ones (a 10M T3 stops climbing at +2M instead of going to +50%). Every
non-skipped bid then adds a 0–`BID_JITTER_MAX` € random offset so the
amounts don't look botty:

    SF ≥ 800             → bid = remaining_cash - jitter           (all-in)
    600 ≤ SF < 800  (T2) → bid = min(price × 1.7, price + 5M) + jitter
    400 ≤ SF < 600  (T3) → bid = min(price × 1.5, price + 2M) + jitter
    300 ≤ SF < 400  (T4) → bid = min(price × 1.2, price + 500K) + jitter
    SF < 300             → skip

Crossover prices (where multiplier == cap): T2 ≈ 7.14M, T3 = 4M,
T4 = 2.5M. Below the crossover the multiplier wins (smaller bid);
above it the cap wins.

Hard rule across every tier: skip the player when the would-be bid
exceeds `remaining_cash` — we never go negative. The all-in tier bids
the full cash regardless of price (a 26M player against 30M cash is
still a ~30M bid).

Idempotency: Cloud Scheduler retries 5xx responses. We log placed bids
to `auto_bid_log/{YYYY-MM-DD}` (one doc per player) and skip anything
in that log before bidding, so a retry of a half-completed run does
not double-bid the players that already went through.
"""

import html
import random
from datetime import datetime, timedelta
from typing import Optional

import requests

from core.constants import MADRID_TZ
from core.sdk import firestore
from core.sdk.jp import get_predict_rate
from core.sdk.telegram import send_telegram_message_or_raise
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.orchestration import build_context
from packages.biwenger_tools.api.logic.player_matching import find_player_match
from packages.biwenger_tools.api.player_formatting import SCORE_SF

logger = get_logger(__name__)

# Tier thresholds + (multiplier, absolute cap) pairs. Kept as module-level
# constants so the unit tests can pin every band without reaching into
# private helpers. Each non-T1 tier bids `min(price × MULT, price + CAP)`
# — see module docstring for the rationale + crossover prices.
TIER_ALL_IN_MIN = 800
TIER_T2_MIN = 600
TIER_T3_MIN = 400
TIER_T4_MIN = 300
TIER_T2_MULTIPLIER = 1.7
TIER_T3_MULTIPLIER = 1.5
TIER_T4_MULTIPLIER = 1.2
TIER_T2_CAP_SURCHARGE = 5_000_000
TIER_T3_CAP_SURCHARGE = 2_000_000
TIER_T4_CAP_SURCHARGE = 500_000

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


def _capped_multiplier_bid(price: int, multiplier: float, cap_surcharge: int) -> int:
    """`min(price × multiplier, price + cap_surcharge)`, cast to int.

    The multiplier bounds the bid on cheap players (a 750K T3 player
    bids 1.125M, not 2.75M); the absolute cap bounds expensive players
    (a 10M T3 bids 12M, not 15M). Result is the smaller of the two."""
    by_multiplier = int(price * multiplier)
    by_cap = price + cap_surcharge
    return min(by_multiplier, by_cap)


def tier_bid(sf: int, price: int, remaining_cash: int) -> tuple[Optional[int], str]:
    """Return `(target_bid, label)` for a player, or `(None, reason)` to skip.

    `target_bid` may exceed `remaining_cash` — the caller is in charge of
    the affordability check (so the skip reason can be richer than a
    bare None).

    Each non-T1 tier bids `min(price × multiplier, price + cap)` so that
    a cheap player doesn't get an absurd absolute surcharge while an
    expensive player doesn't run away with the multiplier. Every tier
    adds (or, for T1 all-in, subtracts) a random 0-`BID_JITTER_MAX` €
    offset so the bid trail stops looking like a bot.
    """
    jitter = _jitter()
    if sf >= TIER_ALL_IN_MIN:
        # All-in on the cash we have right now. Price is irrelevant — the
        # user accepts paying 30M for a 26M player rather than leaving cash
        # on the table. Jitter SUBTRACTS here (can't bid > cash); the result
        # stays strictly inside [remaining_cash - BID_JITTER_MAX, remaining_cash].
        return max(0, remaining_cash - jitter), f"T1 all-in (SF {sf})"
    if sf >= TIER_T2_MIN:
        bid = _capped_multiplier_bid(price, TIER_T2_MULTIPLIER, TIER_T2_CAP_SURCHARGE)
        return bid + jitter, f"T2 (SF {sf})"
    if sf >= TIER_T3_MIN:
        bid = _capped_multiplier_bid(price, TIER_T3_MULTIPLIER, TIER_T3_CAP_SURCHARGE)
        return bid + jitter, f"T3 (SF {sf})"
    if sf >= TIER_T4_MIN:
        bid = _capped_multiplier_bid(price, TIER_T4_MULTIPLIER, TIER_T4_CAP_SURCHARGE)
        return bid + jitter, f"T4 (SF {sf})"
    return None, f"SF {sf} < {TIER_T4_MIN}"


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


def _format_skip_line(entry: dict, esc) -> str:
    """Render one skipped entry. Dispatches on `kind`:

    - `no_cash`     → 💸 with SF + tier label so we can see what we missed.
    - `already_bid` → 🔁 (idempotency replay).
    - `biwenger_reject` → ⚠️ (Biwenger 4xx on the POST).
    - `tier_low` (or missing kind) → ⏭️ + the bare reason string.

    The `no_cash` branch is the user-visible payoff: it stops looking
    like a generic "skip" so a SF 700 / T2 player blocked purely by
    budget is visually distinct from a SF 280 / no-tier player.
    """
    kind = entry.get("kind")
    name = esc(entry["name"])
    if kind == "no_cash":
        # The literal `>` between bid and cash must be pre-escaped as
        # `&gt;` because Telegram's HTML parser reads a bare `>` after
        # whitespace as the end of a tag and rejects the whole message.
        return (
            f"💸 Sin pasta para <b>{name}</b> · "
            f"{esc(entry['tier_label'])} · "
            f"puja {esc(_euros(entry['bid']))} &gt; "
            f"cash {esc(_euros(entry['cash']))}"
        )
    if kind == "already_bid":
        return f"🔁 Ya pujado <b>{name}</b>"
    if kind == "biwenger_reject":
        return f"⚠️ Biwenger rechazó <b>{name}</b>"
    reason = esc(entry.get("reason") or "saltado")
    return f"⏭️ Saltado <b>{name}</b> ({reason})"


def _format_telegram_text(
    day: str,
    placed: list[dict],
    skipped: list[dict],
    total_bid: int,
    remaining_cash: int,
) -> str:
    """Render the per-run summary message the Telegram chat receives.

    Every dynamic value flowing in (player names, tier labels, skip
    reasons) is HTML-escaped because Telegram's HTML parser is strict:
    a stray `<`/`>`/`&` in the body triggers a 400 Bad Request and the
    whole message is dropped. The skip reason
    `"bid 1.000.000 € > cash 500.000 €"` is the canonical trigger.
    """
    esc = lambda s: html.escape(str(s), quote=False)  # noqa: E731

    header_date = datetime.now(MADRID_TZ).strftime("%d/%m %H:%M")
    lines = [f"💸 <b>Pujas automáticas en el mercado — {header_date}</b>", ""]

    for entry in placed:
        lines.append(
            f"✅ Pujado <b>{esc(_euros(entry['bid']))}</b> por "
            f"<b>{esc(entry['name'])}</b> ({esc(entry['tier_label'])})"
        )

    for entry in skipped:
        lines.append(_format_skip_line(entry, esc))

    if not placed and not skipped:
        lines.append("Sin candidatos en el mercado diario.")

    lines.append("")
    lines.append(
        f"Total pujado: <b>{esc(_euros(total_bid))}</b> · "
        f"Cash restante: <b>{esc(_euros(remaining_cash))}</b>"
    )
    if not placed:
        lines.append(f"<i>Log: auto_bid_log/{esc(day)}</i>")
    return "\n".join(lines)


def _maybe_notify(text: str) -> int:
    """Send the summary to Telegram if creds are configured. Returns sent count.

    Lets `TelegramDeliveryError` propagate when Telegram refuses the
    message (4xx parse error, 5xx, timeout). The route handler turns
    it into a 500 so the bot can post a fallback plaintext error to
    the user instead of leaving the chat with an unresolved
    "⏳ procesando…".
    """
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        logger.warning("Telegram credentials missing — skipping send.")
        return 0
    send_telegram_message_or_raise(
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
    ctx = build_context()
    biwenger = ctx.biwenger
    market_players = biwenger.get_market_players(config.MARKET_URL)
    candidates = _build_candidates(market_players, ctx.biwenger_players, ctx.jp_index)

    remaining_cash = int(biwenger.get_account_state().get("cash") or 0)

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
                    "kind": "already_bid",
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
                        "kind": "tier_low",
                        "sf": candidate["sf"],
                        "reason": label,
                    }
                )
            continue
        if target_bid <= 0 or target_bid > remaining_cash:
            # Out-of-budget skip carries the SF + tier label so the summary
            # shows what a richer wallet would have grabbed (and so this skip
            # is visually distinct from a tier_low "irrelevant" skip).
            skipped.append(
                {
                    "player_id": candidate["player_id"],
                    "name": candidate["name"],
                    "kind": "no_cash",
                    "sf": candidate["sf"],
                    "tier_label": label,
                    "bid": target_bid,
                    "cash": remaining_cash,
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
                    "kind": "biwenger_reject",
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
