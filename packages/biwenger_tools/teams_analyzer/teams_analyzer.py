import csv
import os
import time
from datetime import datetime

from packages.biwenger_tools.teams_analyzer import config
from packages.biwenger_tools.teams_analyzer.logic.scrapers import (
    fetch_jp_player_tips,
    fetch_analitica_fantasy_coeffs,
)
from packages.biwenger_tools.teams_analyzer.logic.player_matching import (
    find_player_match,
    normalize_name,
    map_position,
)
from core.sdk.biwenger import BiwengerClient
from core.sdk.telegram import send_telegram_notification
from core.utils import get_logger

logger = get_logger(__name__)


def main():
    """Orquesta el proceso de análisis de equipos y mercado."""
    start_time = time.time()
    logger.info("Script started.", extra={"timestamp": datetime.now().isoformat()})

    try:
        biwenger = BiwengerClient(
            config.BIWENGER_EMAIL,
            config.BIWENGER_PASSWORD,
            config.LOGIN_URL,
            config.ACCOUNT_URL,
            config.LEAGUE_ID,
        )

        players_map_biwenger = biwenger.get_all_players_data_map(config.ALL_PLAYERS_DATA_URL)
        jp_tips_map = fetch_jp_player_tips()
        analitica_coeffs_map = fetch_analitica_fantasy_coeffs()

        if not analitica_coeffs_map:
            logger.error("No Analítica Fantasy data obtained — aborting.")
            return

        managers_map = biwenger.get_league_users(config.LEAGUE_DATA_URL)
        market_players = biwenger.get_market_players(config.MARKET_URL)

        all_players_export_list = []
        logger.info("Analyzing league squads...")

        for manager_id, manager_name in managers_map.items():
            squad_data = biwenger.get_manager_squad(config.USER_SQUAD_URL, manager_id)
            logger.info(
                "Analyzing manager.",
                extra={"manager": manager_name, "players": len(squad_data)},
            )
            time.sleep(0.5)
            for player_data in squad_data:
                player_info = players_map_biwenger.get(player_data.get("id"))
                if not player_info:
                    continue

                player_name = player_info.get("name", "N/A")
                matched_data = find_player_match(player_name, analitica_coeffs_map)

                all_players_export_list.append(
                    {
                        "Mánager": manager_name,
                        "Jugador": player_name,
                        "Posición": map_position(player_info.get("position")),
                        "Valor Actual": player_info.get("price", 0),
                        "Cláusula": player_data.get("owner", {}).get("clause", 0),
                        "Nota IA": jp_tips_map.get(normalize_name(player_name), "Sin datos"),
                        "Coeficiente AF": matched_data["coeficiente"],
                        "Puntuación Esperada AF": matched_data["puntuacion_esperada"],
                    }
                )

        free_agents = [sale for sale in market_players if sale.get("user") is None]
        market_team_name = f"Mercado_{datetime.now().strftime('%d%m%Y')}"
        logger.info(
            "Analyzing free agents.", extra={"team": market_team_name, "count": len(free_agents)}
        )
        for sale in free_agents:
            player_info = players_map_biwenger.get(sale.get("player", {}).get("id"))
            if not player_info:
                continue

            player_name = player_info.get("name", "N/A")
            matched_data = find_player_match(player_name, analitica_coeffs_map)

            all_players_export_list.append(
                {
                    "Mánager": market_team_name,
                    "Jugador": player_name,
                    "Posición": map_position(player_info.get("position")),
                    "Valor Actual": player_info.get("price", 0),
                    "Cláusula": sale.get("price", 0),
                    "Nota IA": jp_tips_map.get(normalize_name(player_name), "Sin datos"),
                    "Coeficiente AF": matched_data["coeficiente"],
                    "Puntuación Esperada AF": matched_data["puntuacion_esperada"],
                }
            )

        if all_players_export_list:
            order = {
                "muyRecomendable": 0,
                "recomendable": 1,
                "apuesta": 2,
                "fondoDeArmario": 3,
                "parche": 4,
                "noRecomendable": 5,
            }
            all_players_export_list.sort(
                key=lambda x: (
                    x["Mánager"].startswith("Mercado_"),
                    x["Mánager"],
                    order.get(x["Nota IA"], 99),
                )
            )

            base_dir = os.path.dirname(os.path.abspath(__file__))
            output_filepath = os.path.join(base_dir, config.FINAL_REPORT_NAME)

            fieldnames = [
                "Mánager",
                "Jugador",
                "Posición",
                "Valor Actual",
                "Cláusula",
                "Nota IA",
                "Coeficiente AF",
                "Puntuación Esperada AF",
            ]
            with open(output_filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_players_export_list)
            logger.info(
                "Export complete.",
                extra={"players": len(all_players_export_list), "file": config.FINAL_REPORT_NAME},
            )

            if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
                caption = f"Análisis de equipos completado ({len(all_players_export_list)} jugadores)"
                send_telegram_notification(
                    config.TELEGRAM_API_URL,
                    config.TELEGRAM_BOT_TOKEN,
                    config.TELEGRAM_CHAT_ID,
                    caption,
                    output_filepath,
                )
    except Exception:
        logger.exception("Unexpected error in teams analyzer.")
    finally:
        duration = time.time() - start_time
        logger.info("Script finished.", extra={"duration_seconds": round(duration, 2)})


if __name__ == "__main__":
    main()
