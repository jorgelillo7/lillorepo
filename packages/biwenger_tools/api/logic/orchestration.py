"""Shared setup for endpoints that talk to JP + Biwenger.

- `build_context()` — full setup: JP health probe, JP index,
  Biwenger session, players map.
- `build_biwenger_session()` — Biwenger only, for handlers that
  don't need JP.
- `require_telegram()` — `(token, chat_id)` if configured, else None.
- `send_image_or_text_fallback()` — sendPhoto with a text fallback so a
  single Telegram refusal in a multi-photo flow doesn't kill the rest.
"""

import time
from dataclasses import dataclass
from typing import Optional, Tuple

from core.sdk.biwenger import BiwengerClient
from core.sdk.jp import check_api_health, fetch_all_players
from core.sdk.telegram import (
    TelegramDeliveryError,
    send_telegram_message,
    send_telegram_photo_or_raise,
)
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.player_matching import build_jp_index

logger = get_logger(__name__)


@dataclass
class OrchestratorContext:
    """Bundle of collaborators every endpoint needs.

    `biwenger_players` is the cf-base player database keyed by id —
    callers must read prices and positions from here (the per-league
    `owner.price` is unreliable for server-side caps).
    """

    biwenger: BiwengerClient
    biwenger_players: dict
    jp_index: dict


def build_context() -> OrchestratorContext:
    """JP health + JP players + JP index + Biwenger session + players map."""
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

    biwenger = build_biwenger_session()
    biwenger_players = biwenger.get_all_players_data_map(config.ALL_PLAYERS_DATA_URL)
    return OrchestratorContext(
        biwenger=biwenger,
        biwenger_players=biwenger_players,
        jp_index=jp_index,
    )


def build_biwenger_session() -> BiwengerClient:
    """Biwenger session only — for handlers that don't need JP / player map."""
    return BiwengerClient(
        config.BIWENGER_EMAIL,
        config.BIWENGER_PASSWORD,
        config.LOGIN_URL,
        config.ACCOUNT_URL,
        config.LEAGUE_ID,
    )


def require_telegram() -> Optional[Tuple[str, str]]:
    """Return `(bot_token, chat_id)` if both are configured, else None."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        logger.warning("Telegram credentials missing — skipping send.")
        return None
    return config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID


def send_image_or_text_fallback(
    token: str, chat_id: str, image: bytes, caption: str
) -> bool:
    """sendPhoto + a small pause to stay under Telegram's send-rate cap.

    Returns True on success. On photo failure (Telegram refusal, network
    blip), sends a short text fallback instead and returns False. Multi-
    photo flows (`/digests/daily`, `/teams` ALL-managers) MUST use this
    instead of `send_telegram_photo_or_raise` — a single broken photo
    would otherwise skip every later step (digest auto-bid, remaining
    manager squads, mercado).
    """
    try:
        send_telegram_photo_or_raise(token, chat_id, image, caption)
        time.sleep(0.5)
        return True
    except TelegramDeliveryError as exc:
        logger.error(
            "Photo delivery failed, sending text fallback.",
            extra={"caption": caption, "error": str(exc)},
        )
        send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text=(
                f"⚠️ <b>{caption}</b> — la foto no salió "
                "(Telegram rechazó el envío). Continúo con el resto."
            ),
        )
        return False
