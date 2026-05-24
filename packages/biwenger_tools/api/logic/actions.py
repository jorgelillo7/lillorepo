"""Handlers for the bot-triggered endpoints (/teams, /market,
/lineups/auto-pick, /managers).

Each function owns one mode end to end: builds the JP index, opens the
Biwenger session, computes the response, and sends the result to Telegram.
The Flask route is a thin shell that calls the right one and translates
exceptions into 5xx.
"""

import time

import requests

from core.sdk.biwenger import BiwengerClient
from core.sdk.jp import check_api_health, fetch_all_players
from core.sdk.telegram import (
    send_telegram_message_or_raise,
    send_telegram_photo_or_raise,
)
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic.image_formatter import build_table_image
from packages.biwenger_tools.api.logic.lineup import (
    format_lineup_message,
    pick_lineup,
)
from packages.biwenger_tools.api.logic.player_matching import build_jp_index
from packages.biwenger_tools.api.logic.rows import build_market_rows, build_squad_rows

logger = get_logger(__name__)


def _send_image(token: str, chat_id: str, image: bytes, caption: str) -> None:
    """sendPhoto + a small pause to stay under Telegram's send-rate cap.

    Raises `TelegramDeliveryError` if Telegram rejects the photo; the
    route handler surfaces it as a 500."""
    send_telegram_photo_or_raise(token, chat_id, image, caption)
    time.sleep(0.5)


def _squad_breakdown(rows: list[dict]) -> dict:
    """Counts of squad rows by JP status — used to debug a `None` lineup pick."""
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
    """`position_id → [player names]` for diagnostics."""
    by_pos: dict[int, list[str]] = {}
    for row in rows:
        pos = row.get("position_id")
        by_pos.setdefault(pos, []).append(row.get("name", "?"))
    return {str(k): v for k, v in by_pos.items()}


def _prepare_context():
    """Boilerplate shared by every action: JP health, JP index, Biwenger client.

    Returns `(biwenger, biwenger_players, jp_index)`.
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
    return biwenger, biwenger_players, jp_index


def _require_telegram() -> tuple[str, str] | None:
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        logger.warning("Telegram credentials missing — skipping send.")
        return None
    return config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID


def run_teams(manager_id: int | None = None) -> dict:
    """Send squad image(s) to Telegram.

    - `manager_id is None` → ALL managers + market (the original
      `/analizar` behaviour, used by the bot's "TODOS" menu choice).
    - `manager_id` set → just that manager's squad; no market. The
      Clausulable/Cláusula columns are included for rivals (not for
      yourself — you already know your own clauses).
    """
    biwenger, biwenger_players, jp_index = _prepare_context()
    telegram = _require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    managers = biwenger.get_league_users(config.LEAGUE_DATA_URL)

    if manager_id is not None:
        # Single-manager mode: one image, no market.
        if manager_id not in managers:
            send_telegram_message_or_raise(
                bot_token=token,
                chat_id=chat_id,
                text=(
                    f"❌ Manager <code>{manager_id}</code> no encontrado en la liga."
                ),
            )
            return {"sent": 0, "reason": "manager_not_found"}
        manager_name = managers[manager_id]
        is_me = manager_id == biwenger.user_id
        squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, manager_id)
        rows = build_squad_rows(
            squad, biwenger_players, jp_index, include_clause=not is_me
        )
        title = "🛡️ Mi equipo" if is_me else f"👤 {manager_name}"
        extra_cols = None if is_me else ["Clausulable", "Cláusula"]
        _send_image(
            token, chat_id, build_table_image(rows, title, extra_cols=extra_cols), title
        )
        logger.info(
            "Single-manager analysis sent.",
            extra={"manager": manager_name, "size": len(rows)},
        )
        return {"sent": 1, "manager": manager_name, "size": len(rows)}

    # All-managers mode (original /analizar): every squad + market.
    my_team: list[dict] = []
    rivals: dict[str, list[dict]] = {}

    for mgr_id, manager_name in managers.items():
        squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, mgr_id)
        logger.info(
            "Squad fetched.",
            extra={"manager": manager_name, "size": len(squad)},
        )
        if mgr_id == biwenger.user_id:
            my_team = build_squad_rows(squad, biwenger_players, jp_index)
        else:
            rivals[manager_name] = build_squad_rows(
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
    market_rows = build_market_rows(market_players, biwenger_players, jp_index)
    _send_image(
        token, chat_id, build_table_image(market_rows, "🛒 Mercado"), "🛒 Mercado"
    )

    logger.info(
        "All-teams analysis sent.",
        extra={"teams": 1 + len(rivals), "market": len(market_rows)},
    )
    return {
        "sent": 2 + len(rivals),
        "teams": 1 + len(rivals),
        "market": len(market_rows),
    }


def list_managers() -> dict:
    """Return the manager list for the league.

    Powers the bot's `/analizar` picker. Plain JSON, no Telegram side
    effects — the bot uses the response to build an inline keyboard.
    Mine is flagged so the bot can present it as "🛡️ Mi equipo".
    """
    biwenger = BiwengerClient(
        config.BIWENGER_EMAIL,
        config.BIWENGER_PASSWORD,
        config.LOGIN_URL,
        config.ACCOUNT_URL,
        config.LEAGUE_ID,
    )
    managers = biwenger.get_league_users(config.LEAGUE_DATA_URL)
    items = [
        {"id": mgr_id, "name": name, "is_me": mgr_id == biwenger.user_id}
        for mgr_id, name in managers.items()
    ]
    items.sort(key=lambda m: (not m["is_me"], m["name"].lower()))
    return {"managers": items}


def run_market() -> dict:
    """Send only the transfer market — used by /market (was /mercado)."""
    biwenger, biwenger_players, jp_index = _prepare_context()
    telegram = _require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    market_players = biwenger.get_market_players(config.MARKET_URL)
    market_rows = build_market_rows(market_players, biwenger_players, jp_index)
    _send_image(token, chat_id, build_table_image(market_rows, "Mercado"), "Mercado")
    logger.info("Market analysis sent.", extra={"size": len(market_rows)})
    return {"sent": 1, "size": len(market_rows)}


def run_auto_pick_lineup(dry_run: bool = False) -> dict:
    """Pick the best lineup, apply it on Biwenger, confirm via Telegram.

    Used by POST /lineups/auto-pick (was /alinear). With `dry_run=True`
    skips the Biwenger PUT and sends the would-be lineup to Telegram as
    a preview — useful before a high-stakes matchday.
    """
    biwenger, biwenger_players, jp_index = _prepare_context()
    telegram = _require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    my_squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
    my_team = build_squad_rows(my_squad, biwenger_players, jp_index)

    by_status = _squad_breakdown(my_team)
    logger.info(
        "Squad ready for auto-pick.",
        extra={"total": len(my_team), **by_status, "dry_run": dry_run},
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
        send_telegram_message_or_raise(
            bot_token=token,
            chat_id=chat_id,
            text="No se pudo calcular la alineacion (jugadores insuficientes).",
        )
        return {"sent": 1, "applied": False, "reason": "no_lineup"}

    if dry_run:
        preview = format_lineup_message(result).replace(
            "✅ Alineación aplicada", "👀 <b>Preview</b> — no aplicada"
        )
        send_telegram_message_or_raise(bot_token=token, chat_id=chat_id, text=preview)
        logger.info(
            "Dry-run lineup preview sent.",
            extra={"formation": result["formation"], "total_sf": result["total_sf"]},
        )
        return {
            "sent": 1,
            "applied": False,
            "dry_run": True,
            "formation": result["formation"],
            "total_sf": result["total_sf"],
        }

    starters_ids = [
        r["bw_id"] for r, _ in sorted(result["starters"], key=lambda rp: rp[1])
    ]
    reserves_ids = [r["bw_id"] if r else None for r in result["reserves"]]
    captain = result.get("captain")
    captain_id = captain["bw_id"] if captain else None
    if captain is None:
        # No starter clears Biwenger's 3M cap on captain MV. Send the lineup
        # anyway with no captain — Biwenger accepts `captain=0` and applies
        # the rest; better than skipping the whole PUT.
        logger.warning(
            "No eligible captain under Biwenger's MV cap — applying without one.",
            extra={"formation": result["formation"], "total_sf": result["total_sf"]},
        )
    try:
        biwenger.set_lineup(
            config.LINEUP_URL,
            result["formation"],
            starters_ids,
            reserves_ids,
            captain_id,
        )
    except requests.RequestException as exc:
        # Biwenger PUT retries internally on transient failures. If we land
        # here the retries also failed (or a 4xx like invalid captain).
        logger.error("set_lineup failed after retries.", extra={"error": str(exc)})
        send_telegram_message_or_raise(
            bot_token=token,
            chat_id=chat_id,
            text=(
                "❌ No se pudo aplicar la alineación en Biwenger.\n"
                f"<code>{exc}</code>\n"
                "Suele ser un blip de la API — vuelve a probar /alinear "
                "en 1-2 minutos."
            ),
        )
        return {"sent": 1, "applied": False, "reason": "biwenger_put_failed"}

    send_telegram_message_or_raise(
        bot_token=token, chat_id=chat_id, text=format_lineup_message(result)
    )
    logger.info(
        "Lineup applied.",
        extra={"formation": result["formation"], "total_sf": result["total_sf"]},
    )
    return {
        "sent": 1,
        "applied": True,
        "formation": result["formation"],
        "total_sf": result["total_sf"],
    }
