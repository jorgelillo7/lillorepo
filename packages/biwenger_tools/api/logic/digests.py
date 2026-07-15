"""Daily digest logic — sends "my team + market + auto-bid + offers inbox" to Telegram.

Used by `POST /digests/daily`, which Cloud Scheduler hits once a day. The
chain (squad → market → bids → offers) is fired in this order so the user
gets a coherent morning briefing in guaranteed sequence, instead of
multiple independent Scheduler jobs racing.

Every step (squad image, market image, auto-bid, offers inbox) is wrapped
in a swallow-on-failure helper so one failing step doesn't lose the rest
of the digest.

The auto-bid step honours `config.AUTO_BID_PAUSED_UNTIL`: while today
(Madrid) is before that date the digest skips it and posts a short pause
note instead. The manual `POST /market/auto-bid` endpoint is not affected.
"""

from datetime import date, datetime

from core.constants import MADRID_TZ
from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import auto_bid, offers
from packages.biwenger_tools.api.logic.image_formatter import build_table_image
from packages.biwenger_tools.api.logic.orchestration import (
    build_context,
    require_telegram,
    send_image_or_text_fallback,
)
from packages.biwenger_tools.api.logic.rows import build_market_rows, build_squad_rows

logger = get_logger(__name__)


def _auto_bid_pause_active() -> bool:
    """True while today (Madrid) is before `config.AUTO_BID_PAUSED_UNTIL`.

    An empty or malformed value means "not paused" — a config typo must
    never silently disable bidding forever.
    """
    raw = (config.AUTO_BID_PAUSED_UNTIL or "").strip()
    if not raw:
        return False
    try:
        resume = date.fromisoformat(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid AUTO_BID_PAUSED_UNTIL %r — ignoring pause.", raw)
        return False
    return datetime.now(MADRID_TZ).date() < resume


def _notify_auto_bid_paused(token: str, chat_id: str) -> None:
    """One-liner so the pause is visible in the chat and not read as a failure."""
    resume = date.fromisoformat(config.AUTO_BID_PAUSED_UNTIL.strip())
    send_telegram_message(
        bot_token=token,
        chat_id=chat_id,
        text=(
            f"⏸️ Pujas automáticas pausadas hasta el {resume.strftime('%d/%m/%Y')}. "
            "Puedes lanzarlas a mano con /pujar."
        ),
    )


def _safe_send_section(token: str, chat_id: str, build_rows, title: str):
    """Build and send one digest table; never raises.

    Returns `(image_sent, row_count)`. On any failure (Biwenger fetch,
    row building, rendering) it logs, posts a short text note so the
    chat shows the section died, and lets the digest continue — the
    remaining sections must still arrive.
    """
    try:
        rows = build_rows()
        sent = send_image_or_text_fallback(
            token, chat_id, build_table_image(rows, title), title
        )
        return sent, len(rows)
    except Exception:
        logger.exception("Digest section failed.", extra={"section": title})
        send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text=(
                f"⚠️ <b>{title}</b> no pudo generarse hoy. "
                "Continúo con el resto del digest."
            ),
        )
        return False, 0


def _safe_run_auto_bid() -> dict:
    """Run auto-bid but never raise — the digest above already shipped."""
    try:
        return auto_bid.run_auto_bid()
    except Exception as exc:
        logger.exception("Auto-bid step failed inside daily digest.")
        return {"error": str(exc)}


def _safe_run_offers_inbox(ctx) -> dict:
    """Run the offers inbox step but never raise. Reuses the digest's ctx
    so we don't pay a second JP+Biwenger round-trip."""
    try:
        return offers.run_offers_inbox(ctx)
    except Exception as exc:
        logger.exception("Offers inbox step failed inside daily digest.")
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

    def _team_rows():
        my_squad = ctx.biwenger.get_manager_squad(
            config.USER_SQUAD_URL, ctx.biwenger.user_id
        )
        return build_squad_rows(my_squad, ctx.biwenger_players, ctx.jp_index)

    def _market_rows():
        market_players = ctx.biwenger.get_market_players(config.MARKET_URL)
        return build_market_rows(market_players, ctx.biwenger_players, ctx.jp_index)

    team_sent, team_count = _safe_send_section(token, chat_id, _team_rows, "Mi equipo")
    market_sent, market_count = _safe_send_section(
        token, chat_id, _market_rows, "Mercado"
    )

    if _auto_bid_pause_active():
        _notify_auto_bid_paused(token, chat_id)
        auto_bid_result = {"paused_until": config.AUTO_BID_PAUSED_UNTIL}
    else:
        auto_bid_result = _safe_run_auto_bid()
    offers_result = _safe_run_offers_inbox(ctx)

    sent_count = int(team_sent) + int(market_sent)
    logger.info(
        "Daily analysis sent.",
        extra={
            "my_team": team_count,
            "market": market_count,
            "images_sent": sent_count,
            "auto_bid_placed": auto_bid_result.get("bid_count"),
            "auto_bid_skipped": auto_bid_result.get("skipped_count"),
            "offers_inbox": offers_result.get("offers"),
            "offers_sent": offers_result.get("sent"),
        },
    )
    return {
        "sent": sent_count,
        "my_team": team_count,
        "market": market_count,
        "auto_bid": auto_bid_result,
        "offers": offers_result,
    }
