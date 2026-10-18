"""The daily digest's trading step: store today's prices, plan, report.

Service layer for `trader.py`. Reuses the rows and rounds the digest already
built, so the step costs one Firestore write, one small Firestore query and
one `/account` read — no extra player or market reads.

`dry_run` plans and reports. `live` acts, in an order that keeps the money
honest: accept the planned sells' offers first, list the squad, then bid
with only the money actually received. Bids already waiting — auto-bid's of
the same morning, or a retried run's — are spent already and never repeated.
Every mutation is attempted once; a failure is reported and the run goes on.
"""

import time
from datetime import datetime

from core.constants import MADRID_TZ
from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import (
    lineup,
    price_history,
    price_history_store,
    trader,
)

logger = get_logger(__name__)

_HISTORY_DAYS = max(config.TRADER_BUY_AFTER_RISES, config.TRADER_SELL_AFTER_FALLS) + 1


def _rules() -> trader.Rules:
    return trader.Rules(
        sell_after_falls=config.TRADER_SELL_AFTER_FALLS,
        buy_after_rises=config.TRADER_BUY_AFTER_RISES,
        buy_margin=config.TRADER_BUY_MARGIN,
        buy_min_sf=config.TRADER_BUY_MIN_SF,
        max_squad=lineup.MAX_SQUAD_SIZE,
        min_squad=config.TRADER_MIN_SQUAD,
        dead_sf=config.TRADER_DEAD_SF,
        hold_days=config.TRADER_HOLD_DAYS,
        max_per_club=config.MAX_PLAYERS_PER_CLUB,
    )


def run(
    ctx,
    squad_rows: list[dict],
    market_rows: list[dict],
    rounds: list[dict] | None,
    *,
    token: str,
    chat_id: str,
    now: float | None = None,
) -> dict:
    """Store today's prices; unless `TRADER_MODE` is `off`, plan the day's
    trades and send the plan to Telegram. Returns a summary for the logs."""
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, MADRID_TZ).date()
    price_history_store.write(today, price_history.prices_of(ctx.biwenger_players))

    mode = config.TRADER_MODE
    if mode == "off":
        return {"mode": "off"}

    history = price_history_store.recent(_HISTORY_DAYS)
    cash = int(ctx.biwenger.get_account_state()["cash"])
    pending = ctx.biwenger.get_my_pending_bids(config.MARKET_URL)
    committed = sum(int(b.get("amount") or 0) for b in pending)
    already_bid = {p for b in pending for p in b.get("requestedPlayers") or []}
    eve = trader.round_eve(rounds, now)
    live = mode == "live"
    if live:
        result = _act(
            ctx,
            squad_rows,
            market_rows,
            history,
            cash,
            committed,
            already_bid,
            eve,
            now,
        )
    else:
        result = trader.plan(
            squad_rows,
            market_rows,
            history,
            cash=cash,
            round_eve=eve,
            negative_limit=config.TRADER_NEGATIVE_LIMIT,
            rules=_rules(),
            committed=committed,
            already_bid=already_bid,
            now=now,
        )
    text = trader.report(result, live=live)
    if len(history) < _HISTORY_DAYS:
        text = (
            f"ℹ️ Solo hay {len(history)} días de precios; hacen falta "
            f"{_HISTORY_DAYS} para ver una subida de "
            f"{config.TRADER_BUY_AFTER_RISES}.\n\n" + text
        )
    send_telegram_message(bot_token=token, chat_id=chat_id, text=text)
    summary = {
        "mode": "live" if live else "dry_run",
        "history_days": len(history),
        "round_eve": result.round_eve,
        "sold" if live else "sells": [m.row["bw_id"] for m in result.sells],
        "bid" if live else "buys": [m.row["bw_id"] for m in result.buys],
        "cash_after": result.cash_after,
    }
    logger.info("Trader planned.", extra=summary)
    return summary


def _act(
    ctx, squad_rows, market_rows, history, cash, committed, already_bid, eve, now
) -> trader.Plan:
    """Sell, list, then bid with what was received. Returns what happened."""
    rules = _rules()
    biwenger = ctx.biwenger
    planned, held, _ = trader.plan_sells(squad_rows, history, rules, now)

    sold: list[trader.Move] = []
    skipped: list[tuple[dict, str]] = []
    inbox = biwenger.get_received_offers()
    for move, offer in trader.sale_offers(planned, inbox, config.TRADER_MIN_SALE_SHARE):
        try:
            settled = biwenger.decide_offer(offer["id"], "accepted")
        except Exception:
            logger.exception("Accepting a sale failed.", extra={"offer": offer["id"]})
            skipped.append((move.row, "la venta no se pudo cerrar"))
            continue
        if (settled or {}).get("status") == "processed":
            sold.append(
                trader.Move(move.row, int(offer["amount"]), move.streak, move.reason)
            )
        else:
            skipped.append((move.row, "Biwenger no cerró la venta"))
    sold_ids = {m.row["bw_id"] for m in sold}
    failed_ids = {row["bw_id"] for row, _ in skipped}
    waiting = [m for m in planned if m.row["bw_id"] not in sold_ids | failed_ids]

    try:
        biwenger.list_squad_for_sale(config.TRADER_LIST_PERCENT)
    except Exception:
        logger.exception("Listing the squad for sale failed.")
        skipped.append(({"name": "La plantilla"}, "no se pudo poner a la venta"))

    floor = 0 if eve else -config.TRADER_NEGATIVE_LIMIT
    keep = [r for r in squad_rows if r["bw_id"] not in sold_ids]
    planned_buys, buy_skips, _ = trader.plan_buys(
        keep,
        market_rows,
        history,
        wallet=cash + sum(m.amount for m in sold) - committed,
        floor=floor,
        rules=rules,
        already_bid=already_bid,
    )
    skipped += buy_skips
    placed: list[trader.Move] = []
    for move in planned_buys:
        try:
            biwenger.place_market_bid(player_id=move.row["bw_id"], amount=move.amount)
        except Exception:
            logger.exception("A bid failed.", extra={"player": move.row["bw_id"]})
            skipped.append((move.row, "Biwenger rechazó la puja"))
            continue
        placed.append(move)

    wallet = cash + sum(m.amount for m in sold) - committed
    wallet -= sum(m.amount for m in placed)
    return trader.Plan(sold, placed, cash, wallet, floor, eve, held, skipped, waiting)
