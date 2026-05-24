"""Shared boilerplate every action / digest / recommendation needs.

Until 2026-05-24 four call sites (`actions._prepare_context`,
`digests.run_daily`, `recommendations.run_recommendations`,
`auto_bid.run_auto_bid`) each reimplemented the same 4-step setup:
JP health probe + fetch all players + build JP index + open a
Biwenger session. This module centralises that.

Two entry points cover every caller:

- `build_context()` — full setup (JP + Biwenger session + players map).
  Used by every endpoint that does real work against the Biwenger /
  JP graph.
- `build_biwenger_session()` — Biwenger session only (no JP, no
  players map). Used by `list_managers` which only needs the league
  users list.

Plus `require_telegram()` for the same opt-in skip-if-credentials-
missing branch that every Telegram-emitting handler needs.
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
    callers should always read prices/positions from here (see memory
    `project_biwenger_prices` for the cf-base vs owner.price rule).
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
    """Return `(bot_token, chat_id)` if both are configured, else None.

    A None return is the signal handlers use to short-circuit before
    doing any work — useful in local dev where Telegram credentials
    are intentionally empty.
    """
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        logger.warning("Telegram credentials missing — skipping send.")
        return None
    return config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID
