"""Orquestador del analizador de equipos.

Flujo:
1. Health-check de la API JP (token / disponibilidad)
2. Descarga jugadores JP (una llamada HTTP)
3. Login Biwenger + descarga: catálogo de jugadores, mánagers, mercado, squads
4. Cruza por nombre normalizado (Biwenger ↔ JP)
5. Envía resumen a Telegram en varios mensajes
"""

import time
from datetime import datetime

from packages.biwenger_tools.teams_analyzer import config
from packages.biwenger_tools.teams_analyzer.logic.player_matching import (
    build_jp_index,
    find_player_match,
)
from packages.biwenger_tools.teams_analyzer.telegram_formatter import build_all_messages
from core.sdk.biwenger import BiwengerClient
from core.sdk.jp import check_api_health, fetch_all_players
from core.sdk.telegram import send_telegram_message
from core.utils import get_logger

logger = get_logger(__name__)


def _build_row(biwenger_player: dict, jp_index: dict) -> dict:
    """Construye una fila lista para el formateador a partir del player Biwenger."""
    name = biwenger_player.get("name", "N/A")
    return {
        "name": name,
        "position_id": biwenger_player.get("position"),
        "price": biwenger_player.get("price", 0),
        "jp_player": find_player_match(name, jp_index),
    }


def main():
    start_time = time.time()
    logger.info("Script started.", extra={"timestamp": datetime.now().isoformat()})

    try:
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

        biwenger_players = biwenger.get_all_players_data_map(
            config.ALL_PLAYERS_DATA_URL
        )
        managers = biwenger.get_league_users(config.LEAGUE_DATA_URL)
        market_players = biwenger.get_market_players(config.MARKET_URL)

        my_team: list[dict] = []
        rivals: dict[str, list[dict]] = {}

        my_user_id = biwenger.user_id

        for manager_id, manager_name in managers.items():
            squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, manager_id)
            logger.info(
                "Squad fetched.", extra={"manager": manager_name, "size": len(squad)}
            )
            time.sleep(0.5)

            rows = []
            for player_data in squad:
                bw_player = biwenger_players.get(player_data.get("id"))
                if not bw_player:
                    continue
                rows.append(_build_row(bw_player, jp_index))

            if manager_id == my_user_id:
                my_team = rows
            else:
                rivals[manager_name] = rows

        market_rows: list[dict] = []
        for sale in market_players:
            if sale.get("user") is not None:
                continue
            bw_player = biwenger_players.get(sale.get("player", {}).get("id"))
            if not bw_player:
                continue
            market_rows.append(_build_row(bw_player, jp_index))

        logger.info(
            "Rows built.",
            extra={
                "my_team": len(my_team),
                "rivals": sum(len(v) for v in rivals.values()),
                "market": len(market_rows),
            },
        )

        messages = build_all_messages(my_team, market_rows, rivals)

        if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
            logger.warning("Telegram credentials missing — skipping send.")
            return

        for msg in messages:
            send_telegram_message(
                config.TELEGRAM_BOT_TOKEN,
                config.TELEGRAM_CHAT_ID,
                msg,
            )
            time.sleep(0.4)  # avoid hitting Telegram rate limits

        logger.info("Telegram messages sent.", extra={"count": len(messages)})

    except Exception:
        logger.exception("Unexpected error in teams analyzer.")
    finally:
        duration = time.time() - start_time
        logger.info("Script finished.", extra={"duration_seconds": round(duration, 2)})


if __name__ == "__main__":
    main()
