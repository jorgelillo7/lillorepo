"""Orquestador del analizador de equipos.

Modos (ANALYSIS_MODE env var):
  daily   — mi equipo + mercado (texto compacto, cron diario)
  all     — todos los equipos como imagen PNG + mercado (/analizar)
  my_team — solo mi equipo (texto compacto) (/myTeam)
  market  — solo mercado (texto compacto) (/mercado)
  alinear — auto-alineacion Biwenger (/alinear)
"""

import math
import time
from datetime import datetime

from packages.biwenger_tools.teams_analyzer import config
from packages.biwenger_tools.teams_analyzer.logic.image_formatter import (
    build_table_image,
)
from packages.biwenger_tools.teams_analyzer.logic.lineup import (
    format_lineup_message,
    pick_lineup,
)
from packages.biwenger_tools.teams_analyzer.logic.player_matching import (
    build_jp_index,
    find_player_match,
)
from core.sdk.biwenger import BiwengerClient
from core.sdk.jp import check_api_health, fetch_all_players
from core.sdk.telegram import (
    send_telegram_message,
    send_telegram_photo,
)
from core.utils import get_logger

logger = get_logger(__name__)


def _clausulable_str(locked_until) -> str:
    if locked_until is None:
        return "Sí"
    remaining_secs = locked_until - time.time()
    if remaining_secs <= 0:
        return "Sí"
    # floor: 11.28 days → 11 (matches "día 21" when today is the 10th)
    # max(1, ...) so sub-day locks still show "No (1d)" instead of "Sí"
    remaining = max(1, math.floor(remaining_secs / 86400))
    return f"No ({remaining}d)"


def _clause_str(clause) -> str:
    if not clause:
        return "-"
    m = int(clause) / 1_000_000
    return f"{m:.1f}M" if int(clause) % 1_000_000 else f"{int(m)}M"


def _build_row(biwenger_player: dict, jp_index: dict) -> dict:
    name = biwenger_player.get("name", "N/A")
    return {
        "bw_id": biwenger_player.get("id"),
        "name": name,
        "position_id": biwenger_player.get("position"),
        "alt_positions": biwenger_player.get("altPositions") or [],
        "price": biwenger_player.get("price", 0),
        "jp_player": find_player_match(name, jp_index),
    }


def _build_market_rows(
    market_players: list, biwenger_players: dict, jp_index: dict
) -> list:
    rows = []
    for sale in market_players:
        if sale.get("user") is not None:
            continue
        bw_player = biwenger_players.get(sale.get("player", {}).get("id"))
        if not bw_player:
            continue
        rows.append(_build_row(bw_player, jp_index))
    return rows


def _build_squad_rows(
    squad: list,
    biwenger_players: dict,
    jp_index: dict,
    include_clause: bool = False,
) -> list:
    rows = []
    for player_data in squad:
        bw_player = biwenger_players.get(player_data.get("id"))
        if not bw_player:
            continue
        row = _build_row(bw_player, jp_index)
        if include_clause:
            owner = player_data.get("owner") or {}
            row["Clausulable"] = _clausulable_str(owner.get("clauseLockedUntil"))
            row["Cláusula"] = _clause_str(owner.get("clause"))
        rows.append(row)
    return rows


def _send_image(token: str, chat_id: str, image: bytes, caption: str) -> None:
    send_telegram_photo(token, chat_id, image, caption)
    time.sleep(0.5)


def main():
    start_time = time.time()
    logger.info(
        "Script started.",
        extra={"timestamp": datetime.now().isoformat(), "mode": config.ANALYSIS_MODE},
    )

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

        if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
            logger.warning("Telegram credentials missing — skipping send.")
            return

        token = config.TELEGRAM_BOT_TOKEN
        chat_id = config.TELEGRAM_CHAT_ID
        mode = config.ANALYSIS_MODE

        if mode == "all":
            managers = biwenger.get_league_users(config.LEAGUE_DATA_URL)
            my_team: list[dict] = []
            rivals: dict[str, list[dict]] = {}

            for manager_id, manager_name in managers.items():
                squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, manager_id)
                logger.info(
                    "Squad fetched.",
                    extra={"manager": manager_name, "size": len(squad)},
                )
                if manager_id == biwenger.user_id:
                    my_team = _build_squad_rows(squad, biwenger_players, jp_index)
                else:
                    rivals[manager_name] = _build_squad_rows(
                        squad, biwenger_players, jp_index, include_clause=True
                    )
                time.sleep(0.5)

            img = build_table_image(my_team, "🛡️ Mi equipo")
            _send_image(token, chat_id, img, "🛡️ Mi equipo")
            for manager_name, rows in rivals.items():
                img = build_table_image(
                    rows,
                    f"👤 {manager_name}",
                    extra_cols=["Clausulable", "Cláusula"],
                )
                _send_image(token, chat_id, img, f"👤 {manager_name}")

            market_players = biwenger.get_market_players(config.MARKET_URL)
            market_rows = _build_market_rows(market_players, biwenger_players, jp_index)
            img = build_table_image(market_rows, "🛒 Mercado")
            _send_image(token, chat_id, img, "🛒 Mercado")

            logger.info(
                "All-teams analysis sent.",
                extra={"teams": 1 + len(rivals), "market": len(market_rows)},
            )

        elif mode == "my_team":
            my_squad = biwenger.get_manager_squad(
                config.USER_SQUAD_URL, biwenger.user_id
            )
            my_team = _build_squad_rows(my_squad, biwenger_players, jp_index)
            img = build_table_image(my_team, "Mi equipo")
            _send_image(token, chat_id, img, "Mi equipo")
            logger.info("My-team analysis sent.", extra={"size": len(my_team)})

        elif mode == "market":
            market_players = biwenger.get_market_players(config.MARKET_URL)
            market_rows = _build_market_rows(market_players, biwenger_players, jp_index)
            img = build_table_image(market_rows, "Mercado")
            _send_image(token, chat_id, img, "Mercado")
            logger.info("Market analysis sent.", extra={"size": len(market_rows)})

        elif mode == "alinear":
            my_squad = biwenger.get_manager_squad(
                config.USER_SQUAD_URL, biwenger.user_id
            )
            my_team = _build_squad_rows(my_squad, biwenger_players, jp_index)
            result = pick_lineup(my_team)
            if result is None:
                send_telegram_message(
                    bot_token=token,
                    chat_id=chat_id,
                    text="No se pudo calcular la alineacion (jugadores insuficientes).",
                )
                return
            starters_ids = [
                r["bw_id"]
                for r, _ in sorted(result["starters"], key=lambda rp: rp[1])
            ]
            reserves_ids = [r["bw_id"] for r in result["reserves"]]
            reserves_ids += [None] * (4 - len(reserves_ids))
            biwenger.set_lineup(
                config.LINEUP_URL,
                result["formation"],
                starters_ids,
                reserves_ids,
                result["captain"]["bw_id"],
            )
            send_telegram_message(
                bot_token=token,
                chat_id=chat_id,
                text=format_lineup_message(result),
            )
            logger.info(
                "Lineup applied.",
                extra={
                    "formation": result["formation"],
                    "total_sf": result["total_sf"],
                },
            )

        else:  # "daily" (default)
            my_squad = biwenger.get_manager_squad(
                config.USER_SQUAD_URL, biwenger.user_id
            )
            my_team = _build_squad_rows(my_squad, biwenger_players, jp_index)
            img = build_table_image(my_team, "Mi equipo")
            _send_image(token, chat_id, img, "Mi equipo")

            market_players = biwenger.get_market_players(config.MARKET_URL)
            market_rows = _build_market_rows(market_players, biwenger_players, jp_index)
            img = build_table_image(market_rows, "Mercado")
            _send_image(token, chat_id, img, "Mercado")

            logger.info(
                "Daily analysis sent.",
                extra={"my_team": len(my_team), "market": len(market_rows)},
            )

    except Exception:
        logger.exception("Unexpected error in teams analyzer.")
    finally:
        duration = time.time() - start_time
        logger.info("Script finished.", extra={"duration_seconds": round(duration, 2)})


if __name__ == "__main__":
    main()
