"""Shared setup for endpoints that talk to JP + Biwenger.

- `build_context()` — full setup: JP health probe, JP index,
  Biwenger session, players map.
- `build_biwenger_session()` — Biwenger only, for handlers that
  don't need JP.
- `require_telegram()` — `(token, chat_id)` if configured, else None.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from core.sdk.biwenger import BiwengerClient
from core.sdk.jp import check_api_health, fetch_all_players
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
