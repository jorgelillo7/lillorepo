"""Daily digest logic — sends "my team + market + auto-bid summary" to Telegram.

Used by `POST /digests/daily`, which Cloud Scheduler hits once a day. The
auto-bid step is chained at the end on purpose: a single daily cron
gives the user a coherent morning message (squad → market → bids) in
guaranteed order, instead of two independent Scheduler jobs racing.
"""

import time

from core.sdk.telegram import send_telegram_photo_or_raise
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import auto_bid
from packages.biwenger_tools.api.logic.image_formatter import build_table_image
from packages.biwenger_tools.api.logic.orchestration import (
    build_context,
    require_telegram,
)
from packages.biwenger_tools.api.logic.rows import build_market_rows, build_squad_rows

logger = get_logger(__name__)


def _send_image(token: str, chat_id: str, image: bytes, caption: str) -> None:
    """sendPhoto + a small pause to stay under Telegram's send-rate cap.

    Raises `TelegramDeliveryError` on Telegram refusal so the route
    handler can surface it as a 500."""
    send_telegram_photo_or_raise(token, chat_id, image, caption)
    time.sleep(0.5)


def _safe_run_auto_bid() -> dict:
    """Wrap `auto_bid.run_auto_bid` so a broken run does not invalidate
    the digest we already sent. The error surfaces in the response."""
    try:
        return auto_bid.run_auto_bid()
    except Exception as exc:
        logger.exception("Auto-bid step failed inside daily digest.")
        return {"error": str(exc)}


def run_daily() -> dict:
    """Send my squad + market images, then chain the auto-bid summary.

    Side effects: hits JP, hits Biwenger, sends 2 PNGs + 1 text message
    to Telegram (via the auto-bid step).
    """
    ctx = build_context()
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    my_squad = ctx.biwenger.get_manager_squad(
        config.USER_SQUAD_URL, ctx.biwenger.user_id
    )
    my_team = build_squad_rows(my_squad, ctx.biwenger_players, ctx.jp_index)
    _send_image(token, chat_id, build_table_image(my_team, "Mi equipo"), "Mi equipo")

    market_players = ctx.biwenger.get_market_players(config.MARKET_URL)
    market_rows = build_market_rows(market_players, ctx.biwenger_players, ctx.jp_index)
    _send_image(token, chat_id, build_table_image(market_rows, "Mercado"), "Mercado")

    auto_bid_result = _safe_run_auto_bid()

    logger.info(
        "Daily analysis sent.",
        extra={
            "my_team": len(my_team),
            "market": len(market_rows),
            "auto_bid_placed": auto_bid_result.get("bid_count"),
            "auto_bid_skipped": auto_bid_result.get("skipped_count"),
        },
    )
    return {
        "sent": 2,
        "my_team": len(my_team),
        "market": len(market_rows),
        "auto_bid": auto_bid_result,
    }
