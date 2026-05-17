"""Orquestador del analizador de equipos.

Modos (ANALYSIS_MODE env var):
  daily   — mi equipo + mercado (cron diario)
  all     — todos los equipos como imagen PNG + mercado (/analizar)
  my_team — solo mi equipo (/myTeam)
  market  — solo mercado (/mercado)
  alinear — auto-alineacion Biwenger (/alinear)
"""

import math
import time
from datetime import datetime

from core.sdk.biwenger import BiwengerClient
from core.sdk.jp import check_api_health, fetch_all_players
from core.sdk.telegram import send_telegram_message, send_telegram_photo
from core.utils import get_logger
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

logger = get_logger(__name__)

SECONDS_PER_DAY = 86400


# ---------------------------------------------------------------------------
# Row builders (pure functions)
# ---------------------------------------------------------------------------


def _clausulable_str(locked_until) -> str:
    if locked_until is None:
        return "Sí"
    remaining_secs = locked_until - time.time()
    if remaining_secs <= 0:
        return "Sí"
    # floor: 11.28 days → 11 (matches "día 21" when today is the 10th)
    # max(1, ...) so sub-day locks still show "No (1d)" instead of "Sí"
    remaining = max(1, math.floor(remaining_secs / SECONDS_PER_DAY))
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


def _squad_breakdown(rows: list[dict]) -> dict:
    """Counts of squad rows by JP status — used to debug a `None` lineup pick.

    Mirrors the exclusion rules in `lineup._is_available`: a row is "available"
    only if it has JP data, is not injured/suspended, has a match this week,
    and JP has not flagged it as `playerInLineup=False`.
    """
    counts = {
        "no_jp": 0,
        "injured": 0,
        "suspended": 0,
        "doubt": 0,
        "no_match": 0,
        "not_in_lineup": 0,
        "available": 0,
    }
    for row in rows:
        jp = row.get("jp_player")
        if jp is None:
            counts["no_jp"] += 1
            continue
        status = jp.get("status", "ok")
        if status == "injured":
            counts["injured"] += 1
            continue
        if status == "suspended":
            counts["suspended"] += 1
            continue
        next_match = jp.get("nextMatch") or {}
        if next_match.get("status") == "break":
            counts["no_match"] += 1
            continue
        if next_match.get("playerInLineup") is False:
            counts["not_in_lineup"] += 1
            continue
        if status == "doubt":
            counts["doubt"] += 1
        counts["available"] += 1
    return counts


def _names_by_position(rows: list[dict]) -> dict:
    """Mapping `position_id → [player names]` for the rows in the squad."""
    by_pos: dict[int, list[str]] = {}
    for row in rows:
        pos = row.get("position_id")
        by_pos.setdefault(pos, []).append(row.get("name", "?"))
    return {str(k): v for k, v in by_pos.items()}


# ---------------------------------------------------------------------------
# Mode handlers — one per ANALYSIS_MODE value. main() picks one and runs it.
# ---------------------------------------------------------------------------


def _run_all_teams(
    biwenger: BiwengerClient,
    biwenger_players: dict,
    jp_index: dict,
    token: str,
    chat_id: str,
) -> None:
    """Send a separate image per manager + market — used by /analizar."""
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

    _send_image(
        token, chat_id, build_table_image(my_team, "🛡️ Mi equipo"), "🛡️ Mi equipo"
    )
    for manager_name, rows in rivals.items():
        img = build_table_image(
            rows, f"👤 {manager_name}", extra_cols=["Clausulable", "Cláusula"]
        )
        _send_image(token, chat_id, img, f"👤 {manager_name}")

    market_players = biwenger.get_market_players(config.MARKET_URL)
    market_rows = _build_market_rows(market_players, biwenger_players, jp_index)
    _send_image(
        token, chat_id, build_table_image(market_rows, "🛒 Mercado"), "🛒 Mercado"
    )

    logger.info(
        "All-teams analysis sent.",
        extra={"teams": 1 + len(rivals), "market": len(market_rows)},
    )


def _run_my_team(
    biwenger: BiwengerClient,
    biwenger_players: dict,
    jp_index: dict,
    token: str,
    chat_id: str,
) -> None:
    """Send only my squad as an image — used by /myTeam."""
    my_squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
    my_team = _build_squad_rows(my_squad, biwenger_players, jp_index)
    _send_image(token, chat_id, build_table_image(my_team, "Mi equipo"), "Mi equipo")
    logger.info("My-team analysis sent.", extra={"size": len(my_team)})


def _run_market(
    biwenger: BiwengerClient,
    biwenger_players: dict,
    jp_index: dict,
    token: str,
    chat_id: str,
) -> None:
    """Send only the transfer market as an image — used by /mercado."""
    market_players = biwenger.get_market_players(config.MARKET_URL)
    market_rows = _build_market_rows(market_players, biwenger_players, jp_index)
    _send_image(token, chat_id, build_table_image(market_rows, "Mercado"), "Mercado")
    logger.info("Market analysis sent.", extra={"size": len(market_rows)})


def _run_alinear(
    biwenger: BiwengerClient,
    biwenger_players: dict,
    jp_index: dict,
    token: str,
    chat_id: str,
) -> None:
    """Pick the best lineup, apply it on Biwenger and confirm via Telegram."""
    my_squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
    my_team = _build_squad_rows(my_squad, biwenger_players, jp_index)

    # Breakdown of the squad so a None lineup is debuggable from Cloud Logging
    # (the picker is silent about *why* a formation can't be filled).
    by_status = _squad_breakdown(my_team)
    logger.info(
        "Squad ready for /alinear.",
        extra={
            "total": len(my_team),
            **by_status,
        },
    )

    result = pick_lineup(my_team)
    if result is None:
        logger.warning(
            "pick_lineup returned None — sending fallback message.",
            extra={
                "total": len(my_team),
                **by_status,
                "names_by_position": _names_by_position(my_team),
            },
        )
        send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text="No se pudo calcular la alineacion (jugadores insuficientes).",
        )
        return

    starters_ids = [
        r["bw_id"] for r, _ in sorted(result["starters"], key=lambda rp: rp[1])
    ]
    reserves_ids = [r["bw_id"] if r else None for r in result["reserves"]]
    biwenger.set_lineup(
        config.LINEUP_URL,
        result["formation"],
        starters_ids,
        reserves_ids,
        result["captain"]["bw_id"],
    )
    send_telegram_message(
        bot_token=token, chat_id=chat_id, text=format_lineup_message(result)
    )
    logger.info(
        "Lineup applied.",
        extra={"formation": result["formation"], "total_sf": result["total_sf"]},
    )


def _run_daily(
    biwenger: BiwengerClient,
    biwenger_players: dict,
    jp_index: dict,
    token: str,
    chat_id: str,
) -> None:
    """Default: send my squad + market — used by the daily cron."""
    my_squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
    my_team = _build_squad_rows(my_squad, biwenger_players, jp_index)
    _send_image(token, chat_id, build_table_image(my_team, "Mi equipo"), "Mi equipo")

    market_players = biwenger.get_market_players(config.MARKET_URL)
    market_rows = _build_market_rows(market_players, biwenger_players, jp_index)
    _send_image(token, chat_id, build_table_image(market_rows, "Mercado"), "Mercado")

    logger.info(
        "Daily analysis sent.",
        extra={"my_team": len(my_team), "market": len(market_rows)},
    )


_MODE_HANDLERS = {
    "all": _run_all_teams,
    "my_team": _run_my_team,
    "market": _run_market,
    "alinear": _run_alinear,
    "daily": _run_daily,
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


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

        handler = _MODE_HANDLERS.get(config.ANALYSIS_MODE, _run_daily)
        handler(
            biwenger,
            biwenger_players,
            jp_index,
            config.TELEGRAM_BOT_TOKEN,
            config.TELEGRAM_CHAT_ID,
        )

    except Exception:
        logger.exception("Unexpected error in teams analyzer.")
    finally:
        duration = time.time() - start_time
        logger.info("Script finished.", extra={"duration_seconds": round(duration, 2)})


if __name__ == "__main__":
    main()
