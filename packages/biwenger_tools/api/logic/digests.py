"""Daily digest logic — sends "my team + market + auto-bid summary" to Telegram.

Used by `POST /digests/daily`, which Cloud Scheduler hits once a day. The
orchestration (JP health check, build index, Biwenger session, send) lives
here so the Flask handler stays a thin shell that translates HTTP errors.

The auto-bid step is chained at the end on purpose: a single daily cron
gives the user a coherent morning message (squad → market → bids) in
guaranteed order, instead of two independent Scheduler jobs racing.
"""

import time

from core.sdk.biwenger import BiwengerClient
from core.sdk.jp import check_api_health, fetch_all_players
from core.sdk.telegram import send_telegram_photo
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import auto_bid
from packages.biwenger_tools.api.logic.image_formatter import build_table_image
from packages.biwenger_tools.api.logic.player_matching import build_jp_index
from packages.biwenger_tools.api.logic.rows import build_market_rows, build_squad_rows

logger = get_logger(__name__)


def _send_image(token: str, chat_id: str, image: bytes, caption: str) -> None:
    """sendPhoto + a small pause to stay under Telegram's send-rate cap."""
    send_telegram_photo(token, chat_id, image, caption)
    time.sleep(0.5)


def run_daily() -> dict:
    """Send my squad + market images. Returns a small summary for the response.

    Side effects: hits JP, hits Biwenger, sends 2 PNGs to Telegram.
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

    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        logger.warning("Telegram credentials missing — skipping send.")
        return {"sent": 0, "reason": "telegram_credentials_missing"}

    my_squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
    my_team = build_squad_rows(my_squad, biwenger_players, jp_index)
    _send_image(
        config.TELEGRAM_BOT_TOKEN,
        config.TELEGRAM_CHAT_ID,
        build_table_image(my_team, "Mi equipo"),
        "Mi equipo",
    )

    market_players = biwenger.get_market_players(config.MARKET_URL)
    market_rows = build_market_rows(market_players, biwenger_players, jp_index)
    _send_image(
        config.TELEGRAM_BOT_TOKEN,
        config.TELEGRAM_CHAT_ID,
        build_table_image(market_rows, "Mercado"),
        "Mercado",
    )

    # Auto-bid chained as the final step so the chat reads: squad → market →
    # bid summary in guaranteed order. Wrapped in a broad try/except — a
    # broken auto-bid run must not lose the digest we already sent above.
    auto_bid_result: dict
    try:
        auto_bid_result = auto_bid.run_auto_bid()
    except Exception as exc:
        logger.exception("Auto-bid step failed inside daily digest.")
        auto_bid_result = {"error": str(exc)}

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
