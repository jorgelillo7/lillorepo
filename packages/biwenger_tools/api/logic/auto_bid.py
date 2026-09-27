"""Daily aggressive auto-bidding on the Biwenger daily market.

`POST /market/auto-bid` (Cloud Scheduler 09:00 Madrid) drives this. We
look at the rotating computer-owned free agents Biwenger exposes every
morning, attach SofaScore (Automanager) ratings from JP, and place a
bid on each player according to the tier below — best score first,
stopping when cash runs out.

Tiers (over Biwenger's cf-base `price`, NOT `owner.price`). Boundaries
are INCLUSIVE on the lower end (a player at exactly 400 lands in T3,
not T4). Each tier bids a flat share over the price, plus a random
0–`BID_JITTER_MAX` € so the amounts don't look botty:

    SF ≥ 700        (T1) → price × 1.40
    550 ≤ SF < 700  (T2) → price × 1.20
    400 ≤ SF < 550  (T3) → price × 1.10
    300 ≤ SF < 400  (T4) → price × 1.05
    SF < 300             → skip

The shares come from the season's resolved market (see `TIER_T*_OVERBID`).

Cash is never exceeded — we never go negative. A T1 or T2 bid that does
not fit becomes the whole wallet (jitter subtracted) as long as the wallet
covers the asking price; otherwise, and for T3 or T4, it is skipped.

Before the ladder sees a candidate, two guards adjust what it reads. A
player who cannot be fielded at all (injured, suspended, no fixture) is
skipped outright, and one who would not make the pitch — JP leaves him out
of its projected eleven, or the squad already has better cover at every
position he plays — has his SF clamped to `BENCH_PRICED_SF` so he cannot
reach T1 or T2. JP scores a benched star highly, and the ladder reads that
number alone; unclamped, a substitute would get the top tiers' premium, and
their whole-wallet bid when cash is short.

Idempotency: Cloud Scheduler retries 5xx responses. We log placed bids
to `auto_bid_log/{YYYY-MM-DD}` (one doc per player) and skip anything
in that log before bidding, so a retry of a half-completed run does
not double-bid the players that already went through.
"""

import html
import os
import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

import requests

from core.constants import MADRID_TZ
from core.sdk import firestore
from core.sdk.telegram import send_telegram_message_or_raise
from core.utils import format_euros, get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.orchestration import build_context
from packages.biwenger_tools.api.logic import rows
from packages.biwenger_tools.api.logic.rows import build_squad_rows
from packages.biwenger_tools.api.player_formatting import availability, shown_score

if TYPE_CHECKING:  # the annotation only; importing it at run time cycles
    from packages.biwenger_tools.api.logic.custom_prediction import ProjectionScale

logger = get_logger(__name__)

# Tier thresholds + (multiplier, absolute cap) pairs. Kept as module-level
# constants so the unit tests can pin every band without reaching into
# private helpers. Each non-T1 tier bids `min(price × MULT, price + CAP)`
# — see module docstring for the rationale + crossover prices.
TIER_ALL_IN_MIN = 700
TIER_T2_MIN = 550
TIER_T3_MIN = 400
TIER_T4_MIN = 300
# Share bid over the price, per tier. Set from the season's resolved market:
# the winning bid was within +5 % of the price in ~75 % of auctions under 5M,
# and the contested stars went for +20-35 % — while the old
# `min(price × mult, price + cap)` ladder paid 6.4M over the runner-up across
# the eight auctions it won.
TIER_T1_OVERBID = 0.40
TIER_T2_OVERBID = 0.20
TIER_T3_OVERBID = 0.10
TIER_T4_OVERBID = 0.05

# How many players deep a position is considered covered. Roughly the most
# any formation fields plus one: no shape uses more than 1 GK, 5 DEF, 6 MID
# or 5 FWD, and carrying one spare of each is the squad you want. A
# candidate who does not beat the Nth-best already owned at every position
# he covers is a bench signing, and gets bid for as one.
SQUAD_DEPTH_SLOTS = {1: 2, 2: 6, 3: 6, 4: 5}

# What a bench signing (or a player JP leaves out of its projected XI) is
# allowed to cost. Both are capped at the T3 ladder no matter how high the
# raw SF is, because the two ways this loses real money are the top tiers'
# premium and their whole-wallet bid:
#
#  - **The whole wallet on a substitute.** Short of cash, T1 and T2 bid
#    everything there is. Doing that on a player the provider says starts on
#    the bench is the single most expensive way to be wrong in this file.
#  - **Paying a starter's premium for depth.** A fourth forward behind three
#    better ones scores from the bench, which in Biwenger is zero.
#
# Capped rather than skipped: a strong player at a covered position is still
# worth owning at the right price — squads change, and the market is the
# only place to buy. The clamp lands one point under T2, i.e. the top of the
# T3 ladder — the most a bench signing can cost.
BENCH_PRICED_SF = TIER_T2_MIN - 1

# The chollos trade. Oráculo's `chollos` shortlist ranks by price rather than
# quality — its players average 1.1M and will never be fielded — so it is
# excluded from the projection bonus and used here instead: bid a thin margin
# over the asking price on every one in the day's market, let the price rise,
# sell. The bid is weak on purpose. Biwenger sells to the highest offer, so
# anyone who actually wants the player outbids this; the ones that land are
# the ones nobody else bid on, which is the premise of the trade rather than a
# flaw in it. The daily ceiling is a safety net, not the control — the owner
# reviews the morning's bids in the app and cancels what does not convince.
# Both read from the environment so the trade can be tuned, or switched off
# entirely with `CHOLLO_MAX_BIDS=0`, without a deploy. It is the one path here
# that spends money on players nobody intends to field, so turning it off must
# not require shipping code.
CHOLLO_MARGIN = int(os.getenv("CHOLLO_MARGIN", "150000"))
CHOLLO_MAX_BIDS = int(os.getenv("CHOLLO_MAX_BIDS", "3"))

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


def _jitter() -> int:
    """Random 0–`BID_JITTER_MAX` € offset for a bid. Indirection makes the
    randomness easy to pin from tests with a single `patch.object`."""
    return random.randint(0, BID_JITTER_MAX)


def tier_bid(
    sf: int, price: int, remaining_cash: int, label_sf: Optional[int] = None
) -> tuple[Optional[int], str]:
    """Return `(target_bid, label)` for a player, or `(None, reason)` to skip.

    Each tier bids its share over the price plus a random 0-`BID_JITTER_MAX`
    € so the trail stops looking like a bot. When a T1 or T2 bid would exceed
    `remaining_cash` but the wallet still covers the asking price, it bids the
    whole wallet instead (jitter subtracted, so never more than the cash):
    skipping a player worth that tier leaves the auction uncontested. Below
    the asking price the market takes no bid, so that case is skipped too.
    A T3 or T4 bid comes back whole even when it does not fit — the caller
    skips it; those players are not worth emptying the wallet for.

    `label_sf` is the score to *print* when it differs from the one being
    priced on — `bid_sf` clamps a substitute's SF to hold him below the
    expensive tiers, and the summary must still report what JP actually
    said about him rather than the clamp.
    """
    jitter = _jitter()
    sf_shown = sf if label_sf is None else label_sf
    for floor, share, tier, whole_wallet in (
        (TIER_ALL_IN_MIN, TIER_T1_OVERBID, "T1", True),
        (TIER_T2_MIN, TIER_T2_OVERBID, "T2", True),
        (TIER_T3_MIN, TIER_T3_OVERBID, "T3", False),
        (TIER_T4_MIN, TIER_T4_OVERBID, "T4", False),
    ):
        if sf < floor:
            continue
        bid = int(price * (1 + share)) + jitter
        if whole_wallet and price <= remaining_cash < bid:
            return (
                max(0, remaining_cash - jitter),
                f"{tier} todo el saldo (SF {sf_shown})",
            )
        return bid, f"{tier} +{share:.0%} (SF {sf_shown})"
    return None, f"SF {sf_shown} < {TIER_T4_MIN}"


def bid_sf(candidate: dict, would_be_bench: bool) -> tuple[int, Optional[str]]:
    """`(sf_for_pricing, reason)` — the SF the tier ladder should read.

    Returns the raw SF and `None` for a candidate who is going to play and
    would walk into the squad. Otherwise clamps him below `TIER_T2_MIN` so
    the ladder prices him as T3 at most, and names which of the two reasons
    applied. See `BENCH_TIER_CAP_MIN` for why capped and not skipped.
    """
    sf = candidate["sf"]
    if sf < TIER_T2_MIN:
        # Already at or below the cap — nothing to clamp, and saying so
        # would put a bewildering note on a bid that never changed.
        return sf, None
    if candidate.get("uncalled"):
        return BENCH_PRICED_SF, "suplente en su equipo"
    if would_be_bench:
        return BENCH_PRICED_SF, "sería suplente en tu plantilla"
    return sf, None


def _build_candidates(
    market_players: list,
    biwenger_players: dict,
    jp_index: dict,
    oraculo_index: dict | None = None,
    oraculo_scale: "ProjectionScale | None" = None,
) -> list[dict]:
    """Daily-market players (computer-owned) enriched with SF + price.

    `sale.get("user") is None` is the marker for daily-market entries;
    user listings carry the seller's id and are out of scope. Anything
    we cannot price (no Biwenger lookup) or cannot score (no JP match)
    is dropped here so the tier loop only sees actionable rows.

    Each candidate also carries `unavailable` (injured, suspended, no
    fixture) and `uncalled` (JP leaves him out of its projected eleven).
    The tier ladder reads a single SF number, and JP hands a high one to
    players in both states — so without these two flags the top tiers
    would pay their premium on a player who is not going to be on the pitch.
    """
    market_rows = []
    for sale in market_players:
        if sale.get("user") is not None:
            continue
        player_ref = sale.get("player") or {}
        bw_player = biwenger_players.get(player_ref.get("id"))
        if not bw_player:
            continue
        market_rows.append(rows.build_row(bw_player, jp_index, oraculo_index))
    rows.enrich_with_custom_prediction(market_rows, oraculo_index, oraculo_scale)

    candidates: list[dict] = []
    for row in market_rows:
        jp_player = row.get("jp_player")
        candidates.append(
            {
                "player_id": row.get("bw_id"),
                "name": row.get("name") or "?",
                "price": int(row.get("price") or 0),
                "sf": shown_score(row) or 0,
                "position_id": row.get("position_id"),
                "alt_positions": row.get("alt_positions") or [],
                "chollo": "chollos" in (row.get("oraculo_lists") or []),
                "unavailable": availability(jp_player) == "out",
                "uncalled": ((jp_player or {}).get("nextMatch") or {}).get(
                    "playerInLineup"
                )
                is False,
            }
        )
    candidates.sort(key=lambda c: c["sf"], reverse=True)
    return candidates


def chollo_bid(candidate: dict) -> tuple[int, str]:
    """A thin margin over the asking price, for a player bought to trade.

    Deliberately outside `tier_bid`. `bid_sf` clamps a would-be substitute to
    `BENCH_PRICED_SF` because the ladder once spent the wallet on a benched star,
    and a chollo is that same shape wearing a different intent — a little,
    knowingly, rather than everything, mistakenly. Giving this path its own
    flat price bypasses the clamp for the trade alone; loosening the clamp
    would reopen the original bug for every candidate.

    Price, not projection: nothing about his SF is consulted, because the
    trade does not care whether he plays.
    """
    return candidate["price"] + CHOLLO_MARGIN + _jitter(), "chollo (especulativo)"


def _chollo_reserve(candidates: list, remaining_cash: int) -> int:
    """Cash held back before the ladder starts, for the day's speculation.

    Sized from the chollos actually on offer this morning rather than a fixed
    figure, which would be too much on a quiet day and too little on a busy
    one. The ladder spends best-first, so "what is left over" is usually
    nothing and the trade would only ever fire on days it was not needed.

    Held back is not spent: a real signing that needs it releases it, because
    one genuine star beats three lottery tickets.
    """
    wanted = [c["price"] + CHOLLO_MARGIN for c in candidates if c.get("chollo")][
        :CHOLLO_MAX_BIDS
    ]
    return min(sum(wanted), remaining_cash)


def _squad_sf_by_position(squad_rows: list) -> dict[int, list[int]]:
    """Projections already owned at each position, best first.

    What a market player is actually worth to this squad depends on who he
    would have to displace. A 450 forward is a signing when the current
    forwards project 200; he is a bench-warmer when they project 600, and
    the tier ladder — which reads his SF and nothing else — prices both the
    same.
    """
    by_pos: dict[int, list[int]] = {}
    for row in squad_rows:
        sf = shown_score(row) or 0
        for pos in {row.get("position_id")} | set(row.get("alt_positions") or []):
            if pos is not None:
                by_pos.setdefault(pos, []).append(sf)
    for sfs in by_pos.values():
        sfs.sort(reverse=True)
    return by_pos


def _would_be_bench(candidate: dict, by_pos: dict[int, list[int]]) -> bool:
    """Whether this signing would sit behind the players already owned.

    "Behind" is measured against `SQUAD_DEPTH_SLOTS` per position rather
    than the starting eleven, because the eleven's shape moves week to week:
    a squad carrying three forwards who all out-project him does not need a
    fourth at any formation the optimizer might pick.

    Unknown positions count as *not* bench — a signal we do not have must
    not quietly suppress a bid.
    """
    positions = {candidate.get("position_id")} | set(
        candidate.get("alt_positions") or []
    )
    positions = {p for p in positions if p is not None}
    if not positions:
        return False
    # He is bench only if he fails to break into the depth chart at EVERY
    # position he covers — a versatile player needs one door open, not all.
    for pos in positions:
        owned = by_pos.get(pos) or []
        if len(owned) < SQUAD_DEPTH_SLOTS.get(pos, 4):
            return False
        if candidate["sf"] > owned[SQUAD_DEPTH_SLOTS.get(pos, 4) - 1]:
            return False
    return True


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
            # deletes the doc once this timestamp is in the past. Shift in UTC:
            # adding a timedelta to a ZoneInfo-aware datetime is DST-naive, so a
            # window that crosses a DST change would drift the instant by ±1h.
            "expires_at": now.astimezone(timezone.utc) + timedelta(days=_LOG_TTL_DAYS),
        },
    )


def _format_skip_line(entry: dict, esc) -> str:
    """Render one skipped entry. Dispatches on `kind`:

    - `no_cash`     → 💸 with SF + tier label so we can see what we missed.
    - `already_bid` → 🔁 (idempotency replay).
    - `unavailable` → 🚑 (injured, suspended or no fixture).
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
            f"puja {esc(format_euros(entry['bid']))} &gt; "
            f"cash {esc(format_euros(entry['cash']))}"
        )
    if kind == "already_bid":
        return f"🔁 Ya pujado <b>{name}</b>"
    if kind == "unavailable":
        return f"🚑 No disponible <b>{name}</b> · SF {esc(entry.get('sf', 0))}"
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
            f"✅ Pujado <b>{esc(format_euros(entry['bid']))}</b> por "
            f"<b>{esc(entry['name'])}</b> ({esc(entry['tier_label'])})"
        )

    for entry in skipped:
        lines.append(_format_skip_line(entry, esc))

    if not placed and not skipped:
        lines.append("Sin candidatos en el mercado diario.")

    lines.append("")
    lines.append(
        f"Total pujado: <b>{esc(format_euros(total_bid))}</b> · "
        f"Cash restante: <b>{esc(format_euros(remaining_cash))}</b>"
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
    candidates = _build_candidates(
        market_players,
        ctx.biwenger_players,
        ctx.jp_index,
        oraculo_index=ctx.oraculo_index,
        oraculo_scale=ctx.oraculo_scale,
    )

    # What we already own, so a bid can be priced against the squad instead
    # of in a vacuum. Best-effort: without it every candidate simply prices
    # off his own SF, which is the behaviour this used to have.
    try:
        my_squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
        squad_by_pos = _squad_sf_by_position(
            build_squad_rows(
                my_squad,
                ctx.biwenger_players,
                ctx.jp_index,
                oraculo_index=ctx.oraculo_index,
                oraculo_scale=ctx.oraculo_scale,
            )
        )
    except Exception:
        logger.exception("Squad fetch failed — bidding without the depth signal.")
        squad_by_pos = {}

    remaining_cash = int(biwenger.get_account_state().get("cash") or 0)

    day = _today_madrid()
    already_bid = _already_bid_ids(day)

    # Held back before the ladder starts. Candidates arrive best-first, so a
    # signing that needs the reserve is met before any chollo and takes what
    # it needs of it on the way past.
    reserve = _chollo_reserve(candidates, remaining_cash)
    chollo_bids = 0

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

        if candidate["unavailable"]:
            skipped.append(
                {
                    "player_id": candidate["player_id"],
                    "name": candidate["name"],
                    "kind": "unavailable",
                    "sf": candidate["sf"],
                }
            )
            continue

        # Price him against the squad before the ladder sees him, so a
        # substitute cannot reach T1 or T2 on his raw SF alone.
        priced_sf, cap_reason = bid_sf(
            candidate, _would_be_bench(candidate, squad_by_pos)
        )
        spendable = remaining_cash - reserve
        # Priced against the whole wallet: a T1/T2 short of cash bids all of
        # it, and the reserve below gives way to that as to any real signing.
        target_bid, label = tier_bid(
            priced_sf, candidate["price"], remaining_cash, label_sf=candidate["sf"]
        )
        if cap_reason:
            label = f"{label} · rebajado: {cap_reason}"
        if (
            target_bid is not None
            and not candidate.get("chollo")
            and priced_sf >= TIER_T3_MIN
            and target_bid > spendable
            and target_bid <= remaining_cash
        ):
            # The reserve yields to a real signing — skipping one to keep
            # three lottery tickets alive is the trade backwards — but only
            # down to T3. Below that the ladder is buying squad filler, and a
            # ticket with an explicit exit (sell when the price
            # rises) is worth more than a marginal body. It gives way exactly
            # as far as this bid needs and no further.
            reserve = max(0, remaining_cash - target_bid)
            spendable = remaining_cash - reserve
        if target_bid is None and candidate.get("chollo"):
            speculative, label = chollo_bid(candidate)
            if chollo_bids < CHOLLO_MAX_BIDS and speculative <= remaining_cash:
                target_bid = speculative
                reserve = max(0, reserve - speculative)
                chollo_bids += 1
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
        affordable = remaining_cash if candidate.get("chollo") else spendable
        if target_bid <= 0 or target_bid > affordable:
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
