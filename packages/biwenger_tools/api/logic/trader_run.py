"""The daily digest's trading step: store today's prices, plan, report.

Service layer for `trader.py`. Reuses the rows and rounds the digest already
built, so the step costs one Firestore write, one small Firestore query and
one `/account` read — no extra player or market reads.

Phase A of `.claude/plans/market-trader.md`: every mode short of `off` only
plans and reports. Nothing here places a bid or accepts an offer yet; `live`
is read as `dry_run` until the list-for-sale endpoint is known.
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
    if mode == "live":
        logger.warning("TRADER_MODE=live is not built yet; planning only.")

    history = price_history_store.recent(_HISTORY_DAYS)
    cash = int(ctx.biwenger.get_account_state()["cash"])
    result = trader.plan(
        squad_rows,
        market_rows,
        history,
        cash=cash,
        round_eve=trader.round_eve(rounds, now),
        negative_limit=config.TRADER_NEGATIVE_LIMIT,
        rules=_rules(),
    )
    text = trader.report(result, live=False)
    if len(history) < _HISTORY_DAYS:
        text = (
            f"ℹ️ Solo hay {len(history)} días de precios; hacen falta "
            f"{_HISTORY_DAYS} para ver una subida de "
            f"{config.TRADER_BUY_AFTER_RISES}.\n\n" + text
        )
    send_telegram_message(bot_token=token, chat_id=chat_id, text=text)
    summary = {
        "mode": "dry_run",
        "history_days": len(history),
        "round_eve": result.round_eve,
        "sells": [m.row["bw_id"] for m in result.sells],
        "buys": [m.row["bw_id"] for m in result.buys],
        "cash_after": result.cash_after,
    }
    logger.info("Trader planned.", extra=summary)
    return summary
