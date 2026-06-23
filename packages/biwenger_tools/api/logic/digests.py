"""Daily digest logic — sends "my team + market + auto-bid summary" to Telegram.

Used by `POST /digests/daily`, which Cloud Scheduler hits once a day. The
auto-bid step is chained at the end on purpose: a single daily cron
gives the user a coherent morning message (squad → market → bids) in
guaranteed order, instead of two independent Scheduler jobs racing.
"""

import time

from core.sdk.telegram import (
    TelegramDeliveryError,
    send_telegram_message,
    send_telegram_photo_or_raise,
)
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


def _send_image_or_text_fallback(
    token: str, chat_id: str, image: bytes, caption: str
) -> bool:
    """sendPhoto + a small pause to stay under Telegram's send-rate cap.

    Returns True on success. On photo failure (Telegram refusal, network
    blip), sends a short text fallback instead and returns False. The
    digest must NOT raise here — a single broken photo would otherwise
    skip every later step (mercado, auto-bid). The user gets nothing.
    The text fallback at least flags that something rendered but couldn't
    be delivered as image so the auto-bid still runs.
    """
    try:
        send_telegram_photo_or_raise(token, chat_id, image, caption)
        time.sleep(0.5)
        return True
    except TelegramDeliveryError as exc:
        logger.error(
            "Digest: photo delivery failed, sending text fallback.",
            extra={"caption": caption, "error": str(exc)},
        )
        send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text=(
                f"⚠️ <b>{caption}</b> — la foto no salió "
                "(Telegram rechazó el envío). Continúo con el resto del digest."
            ),
        )
        return False


def _safe_run_auto_bid() -> dict:
    """Run auto-bid but never raise — the digest above already shipped."""
    try:
        return auto_bid.run_auto_bid()
    except Exception as exc:
        logger.exception("Auto-bid step failed inside daily digest.")
        return {"error": str(exc)}


def _notify_digest_failure(exc: Exception) -> None:
    """Best-effort error notification when `run_daily` blows up.

    Run after the digest's own try/except so the user gets at least a
    "today's batch failed because X" message instead of silence. The send
    itself swallows exceptions — if Telegram is the source of the failure
    there is nothing more we can do.
    """
    telegram = require_telegram()
    if telegram is None:
        return
    token, chat_id = telegram
    try:
        send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text=(
                "🚨 <b>Digest diario falló</b>\n"
                f"<code>{type(exc).__name__}: {exc}</code>\n"
                "Las pujas automáticas pueden no haberse ejecutado."
            ),
        )
    except Exception:
        logger.exception("Failed to notify Telegram of digest failure.")


def run_daily() -> dict:
    """Send my squad + market images, then chain the auto-bid summary.

    Side effects: hits JP, hits Biwenger, sends 2 PNGs + 1 text message
    to Telegram (via the auto-bid step). Top-level errors are surfaced
    to Telegram before propagating so the user never gets silent
    failures like the 22/06–23/06 incidents.
    """
    try:
        return _run_daily_inner()
    except Exception as exc:
        _notify_digest_failure(exc)
        raise


def _run_daily_inner() -> dict:
    ctx = build_context()
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    my_squad = ctx.biwenger.get_manager_squad(
        config.USER_SQUAD_URL, ctx.biwenger.user_id
    )
    my_team = build_squad_rows(my_squad, ctx.biwenger_players, ctx.jp_index)
    team_sent = _send_image_or_text_fallback(
        token, chat_id, build_table_image(my_team, "Mi equipo"), "Mi equipo"
    )

    market_players = ctx.biwenger.get_market_players(config.MARKET_URL)
    market_rows = build_market_rows(market_players, ctx.biwenger_players, ctx.jp_index)
    market_sent = _send_image_or_text_fallback(
        token, chat_id, build_table_image(market_rows, "Mercado"), "Mercado"
    )

    auto_bid_result = _safe_run_auto_bid()

    sent_count = int(team_sent) + int(market_sent)
    logger.info(
        "Daily analysis sent.",
        extra={
            "my_team": len(my_team),
            "market": len(market_rows),
            "images_sent": sent_count,
            "auto_bid_placed": auto_bid_result.get("bid_count"),
            "auto_bid_skipped": auto_bid_result.get("skipped_count"),
        },
    )
    return {
        "sent": sent_count,
        "my_team": len(my_team),
        "market": len(market_rows),
        "auto_bid": auto_bid_result,
    }
