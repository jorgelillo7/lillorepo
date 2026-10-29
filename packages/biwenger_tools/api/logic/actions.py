"""Handlers for the bot-triggered endpoints (/teams, /market,
/lineups/auto-pick, /managers).

Each function owns one mode end to end: builds the JP index, opens the
Biwenger session, computes the response, and sends the result to Telegram.
The Flask route is a thin shell that calls the right one and translates
exceptions into 5xx.
"""

import time
from datetime import datetime

import requests

from core.constants import MADRID_TZ
from core.sdk.biwenger import BiwengerClient
from core.sdk.telegram import (
    send_telegram_message,
    send_telegram_message_or_raise,
    send_telegram_photo_or_raise,
)
from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import (
    board_archive_store,
    draft,
    fixture_run,
    league_cash,
    league_compare,
    pact_store,
    projection_ledger_capture,
    public_cache,
    public_members_store,
    round_context,
    trader,
)
from packages.biwenger_tools.api.logic import lineup as lineup_logic
from packages.biwenger_tools.api.logic.draft_service.managers import (
    names_by_telegram_id as draft_names_by_telegram_id,
)
from packages.biwenger_tools.api.logic.image_formatter import (
    build_cash_image,
    build_table_image,
)
from packages.biwenger_tools.api.logic.lineup import (
    format_lineup_message,
    format_preview_message,
    pick_lineup,
)
from packages.biwenger_tools.api.logic.orchestration import (
    build_biwenger_session,
    build_context,
    require_telegram,
    send_image_or_text_fallback,
)
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
        "sanctioned": 0,
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
        if status == "sanctioned":
            counts["sanctioned"] += 1
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
    by_pos: dict[int | None, list[str]] = {}
    for row in rows:
        pos = row.get("position_id")
        by_pos.setdefault(pos, []).append(row.get("name", "?"))
    return {str(k): v for k, v in by_pos.items()}


# Shared setup helpers live in `orchestration` — `build_context()` for the
# JP+Biwenger combo, `require_telegram()` for the credential gate.


def run_teams(manager_id: int | None = None) -> dict:
    """Send squad image(s) to Telegram.

    - `manager_id is None` → ALL managers + market (the original
      `/analizar` behaviour, used by the bot's "TODOS" menu choice).
    - `manager_id` set → just that manager's squad; no market. The
      Clausulable/Cláusula columns are included for rivals (not for
      yourself — you already know your own clauses).
    """
    ctx = build_context()
    biwenger, biwenger_players, jp_index, oraculo_index, oraculo_scale = (
        ctx.biwenger,
        ctx.biwenger_players,
        ctx.jp_index,
        ctx.oraculo_index,
        ctx.oraculo_scale,
    )
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    managers = biwenger.get_league_users(
        config.LEAGUE_DATA_URL, config.NON_PLAYING_MEMBER_IDS
    )
    upcoming = read_fixture_runs(biwenger)

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
            squad,
            biwenger_players,
            jp_index,
            oraculo_index,
            include_clause=not is_me,
            oraculo_scale=oraculo_scale,
        )
        title = "🛡️ Mi equipo" if is_me else f"👤 {manager_name}"
        _send_image(
            token, chat_id, _squad_image(rows, title, upcoming, not is_me), title
        )
        logger.info(
            "Single-manager analysis sent.",
            extra={"manager": manager_name, "size": len(rows)},
        )
        return {"sent": 1, "manager": manager_name, "size": len(rows)}

    # All-managers mode (original /analizar): every squad + market.
    # Uses `send_image_or_text_fallback` so a single Telegram refusal
    # doesn't kill the rest of the run — with 10+ sequential photo
    # uploads, compounding flakiness used to leave the user with a
    # partial output and a generic "❌ Error" from the bot.
    my_team: list[dict] = []
    rivals: dict[str, list[dict]] = {}

    for mgr_id, manager_name in managers.items():
        squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, mgr_id)
        logger.info(
            "Squad fetched.",
            extra={"manager": manager_name, "size": len(squad)},
        )
        if mgr_id == biwenger.user_id:
            my_team = build_squad_rows(
                squad,
                biwenger_players,
                jp_index,
                oraculo_index,
                oraculo_scale=oraculo_scale,
            )
        else:
            rivals[manager_name] = build_squad_rows(
                squad,
                biwenger_players,
                jp_index,
                oraculo_index,
                include_clause=True,
                oraculo_scale=oraculo_scale,
            )
        time.sleep(0.5)

    sent_count = 0
    if send_image_or_text_fallback(
        token,
        chat_id,
        _squad_image(my_team, "🛡️ Mi equipo", upcoming, clauses=False),
        "🛡️ Mi equipo",
    ):
        sent_count += 1
    for manager_name, rows in rivals.items():
        img = _squad_image(rows, f"👤 {manager_name}", upcoming, clauses=True)
        if send_image_or_text_fallback(token, chat_id, img, f"👤 {manager_name}"):
            sent_count += 1

    # The squads are already in the chat by now, so a market failure must not
    # turn the whole run into a 500 — the user would see every photo arrive and
    # then a bare error. The market is also the section most likely to fail:
    # it is off-season for months a year, and Biwenger answers a disabled
    # market with a payload that carries no sales at all.
    market_rows: list[dict] = []
    try:
        market_players = biwenger.get_market_players(config.MARKET_URL)
        market_rows = build_market_rows(
            market_players,
            biwenger_players,
            jp_index,
            oraculo_index,
            oraculo_scale=oraculo_scale,
        )
        image = _market_image(market_rows, "🛒 Mercado", upcoming)
        if send_image_or_text_fallback(token, chat_id, image, "🛒 Mercado"):
            sent_count += 1
    except Exception:
        logger.exception("Market section failed; squads already sent.")
        send_telegram_message(
            bot_token=token,
            chat_id=chat_id,
            text="⚠️ <b>Mercado</b> no disponible. Los equipos sí han salido.",
        )

    logger.info(
        "All-teams analysis sent.",
        extra={
            "teams": 1 + len(rivals),
            "market": len(market_rows),
            "images_sent": sent_count,
        },
    )
    return {
        "sent": sent_count,
        "teams": 1 + len(rivals),
        "market": len(market_rows),
    }


def list_managers() -> dict:
    """Return the manager list for the league.

    Powers the bot's `/analizar` picker. Plain JSON, no Telegram side
    effects — the bot uses the response to build an inline keyboard.
    Mine is flagged so the bot can present it as "🛡️ Mi equipo".
    """
    biwenger = build_biwenger_session()
    managers = biwenger.get_league_users(
        config.LEAGUE_DATA_URL, config.NON_PLAYING_MEMBER_IDS
    )
    items = [
        {"id": mgr_id, "name": name, "is_me": mgr_id == biwenger.user_id}
        for mgr_id, name in managers.items()
    ]
    items.sort(key=lambda m: (not m["is_me"], m["name"].lower()))
    return {"managers": items}


def list_pact_managers() -> dict:
    """League managers, each flagged with whether the pact protects them.

    Backs the bot's `/pacto` picker: one screen showing who is currently off
    limits, with a button per manager. Same shape as `list_managers` plus
    `pacted`, so the bot can build the keyboard from one call.
    """
    protected = pact_store.load()
    managers = list_managers()["managers"]
    for manager in managers:
        manager["pacted"] = manager["id"] in protected
    return {"managers": managers}


def toggle_pact(manager_id: int) -> dict:
    """Add or remove one manager from the non-aggression pact.

    Returns the manager's new state and the refreshed list, so the bot can
    redraw the picker in place without a second round trip.
    """
    protected = pact_store.toggle(int(manager_id))
    return {"manager_id": int(manager_id), "pacted": protected, **list_pact_managers()}


def run_market() -> dict:
    """Send only the transfer market — used by /market (was /mercado)."""
    ctx = build_context()
    biwenger, biwenger_players, jp_index, oraculo_index, oraculo_scale = (
        ctx.biwenger,
        ctx.biwenger_players,
        ctx.jp_index,
        ctx.oraculo_index,
        ctx.oraculo_scale,
    )
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    market_players = biwenger.get_market_players(config.MARKET_URL)
    market_rows = build_market_rows(
        market_players,
        biwenger_players,
        jp_index,
        oraculo_index,
        oraculo_scale=oraculo_scale,
    )
    image = _market_image(market_rows, "Mercado", read_fixture_runs(biwenger))
    _send_image(token, chat_id, image, "Mercado")
    logger.info("Market analysis sent.", extra={"size": len(market_rows)})
    return {"sent": 1, "size": len(market_rows)}


def run_league_compare() -> dict:
    """Send the league's squads ranked by value and by projection.

    Owner-only by construction: it goes to `TELEGRAM_CHAT_ID`, never to the
    draft group. Handing every rival the projection of their own squad would
    give away the only edge the tooling provides.
    """
    ctx = build_context()
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    summary = league_compare.collect_cached(ctx)
    if not summary:
        return {"sent": 0, "reason": "no_squads"}
    today = datetime.now(MADRID_TZ).strftime("%d/%m")
    send_telegram_message_or_raise(
        bot_token=token,
        chat_id=chat_id,
        text=league_compare.render(
            summary,
            title=f"📊 <b>La liga hoy</b> · {today}",
            note=(
                "Valor de mercado actual y SF del mejor once que puede alinear "
                "cada uno (JP + Oráculo, como en tus imágenes); entre paréntesis, "
                "la plantilla entera. Van sin combinar porque son dos preguntas "
                "distintas: un equipo caro no es un equipo que puntúe."
            ),
        ),
    )
    logger.info("League comparison sent.", extra={"managers": len(summary)})
    return {"sent": 1, "managers": len(summary)}


_PROTECTION_WINDOW_S = 24 * 3600


def _archived_board() -> list[dict] | None:
    """The season's board archive; None, logged, when it cannot be read — the
    live board still answers, and the image says the archive was missing."""
    try:
        return board_archive_store.load(config.CURRENT_SEASON)
    except Exception:
        logger.exception("Could not read the board archive — live board only.")
        return None


def _league_money(
    biwenger, players: dict
) -> tuple[list[dict], dict, "league_cash.CashBook", int, int | None]:
    """Every playing manager's cash and max bid, rebuilt from the board and
    its archive.

    Returns `(rows, squads_by_manager_id, book, board_entries, lost)`; rows
    carry `id`, `name`, `cash`, `in_clauses`, `recoverable`, `max_bid`,
    `is_me`; `lost` is how many archived entries the live board no longer
    returns, None when the archive could not be read. ~12 sequential reads.
    """
    live = biwenger.get_all_board_messages(
        config.LEAGUE_BOARD_ALL_URL, until_type=league_cash.SEASON_START_TYPE
    )
    archived = _archived_board()
    entries, lost = league_cash.with_archive(live, archived or [])
    book = league_cash.rebuild(entries, draft.DEFAULT_BUDGET)
    managers = biwenger.get_league_users(
        config.LEAGUE_DATA_URL, config.NON_PLAYING_MEMBER_IDS
    )
    rows, squads = [], {}
    for manager_id, name in managers.items():
        squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, manager_id)
        squads[manager_id] = squad
        cash = book.cash_of(manager_id)
        invested = league_cash.in_clauses(squad)
        rows.append(
            {
                "id": manager_id,
                "name": name,
                "cash": cash,
                "in_clauses": invested,
                "recoverable": league_cash.recoverable(invested),
                "max_bid": league_cash.max_bid(
                    cash, league_cash.squad_value(squad, players)
                ),
                "is_me": manager_id == biwenger.user_id,
            }
        )
    return rows, squads, book, len(entries), (None if archived is None else lost)


def _rivals(money_rows: list[dict]) -> list[dict]:
    """The other managers, each flagged when the non-aggression pact covers
    them. A pact read that fails costs the flag, never the answer."""
    try:
        pacted = pact_store.load()
    except Exception:
        logger.exception("Could not read the pact — rivals go unflagged.")
        pacted = set()
    return [
        {**row, "pacted": row["id"] in pacted} for row in money_rows if not row["is_me"]
    ]


def _my_clause_rows(ctx, squad: list) -> list[dict]:
    return build_squad_rows(
        squad,
        ctx.biwenger_players,
        ctx.jp_index,
        ctx.oraculo_index,
        include_clause=True,
        oraculo_scale=ctx.oraculo_scale,
    )


_CASH_KEY = "league_cash"
_MOVEMENTS_KEY = "movements"


def _cash_figures(biwenger, players: dict) -> tuple[dict, dict, list[dict]]:
    """The public part of `/saldos` — `{rows, notes, self_check_ok, ...}`,
    plain JSON so the cache can hold it — plus the squads and raw money rows
    the owner's exposure block needs."""
    money, squads, book, n_entries, lost = _league_money(biwenger, players)
    real_mine = biwenger.get_account_state()["cash"]
    rebuilt_mine = book.cash_of(biwenger.user_id)
    figures = {
        "rows": league_cash.ranked(money),
        "notes": league_cash.notes(book.unknown_types, rebuilt_mine, real_mine, lost),
        "self_check_ok": rebuilt_mine == real_mine,
        "board_entries": n_entries,
        "unknown_types": sorted(book.unknown_types),
        "archive_lost": lost,
    }
    return figures, squads, money


def _cash_title() -> str:
    return f"💰 Saldos · {datetime.now(MADRID_TZ).strftime('%d/%m %H:%M')}"


def run_league_cash() -> dict:
    """Send every manager's cash and maximum bid, rebuilt from the board, with
    the owner's three best-projected players and who can reach their clause.

    Owner-only, like `/comparar`: the league hides these figures from all its
    members. Always read fresh — the owner reads it right after a clausulazo —
    and the read refreshes the cache the public `/saldos` draws on.
    """
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    ctx = build_context()
    biwenger = ctx.biwenger
    figures, squads, money = _cash_figures(biwenger, ctx.biwenger_players)
    public_cache.refresh(_CASH_KEY, figures)
    top = league_cash.exposed(_my_clause_rows(ctx, squads[biwenger.user_id]), 3)
    exposure = league_cash.exposure_rows(top, _rivals(money))
    title = _cash_title()
    image = build_cash_image(
        figures["rows"], title, figures["notes"], exposure=exposure
    )
    send_telegram_photo_or_raise(token, chat_id, image, title)
    logger.info(
        "League cash sent.",
        extra={
            "managers": len(money),
            "board_entries": figures["board_entries"],
            "self_check_ok": figures["self_check_ok"],
            "unknown_types": figures["unknown_types"],
            "archive_lost": figures["archive_lost"],
        },
    )
    return {
        "sent": 1,
        "managers": len(money),
        "self_check_ok": figures["self_check_ok"],
        "unknown_types": figures["unknown_types"],
    }


_UNAVAILABLE = "⚠️ {what} no disponible ahora. Prueba en unos minutos."


def _public_reply_unavailable(chat_id: str, what: str) -> dict:
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=chat_id,
        text=_UNAVAILABLE.format(what=what),
    )
    return {"sent": 1, "unavailable": True}


def _read_public_cash() -> dict:
    """A fresh read without JP or Oráculo: the public table needs neither."""
    biwenger = build_biwenger_session()
    players, _ = BiwengerClient.get_competition_maps(config.ALL_PLAYERS_DATA_URL)
    figures, _, _ = _cash_figures(biwenger, players)
    return figures


def run_public_league_cash(chat_id: str) -> dict:
    """`/saldos` for an allowlisted member: the league table and notes, never
    the owner's exposure block, sent to the chat that asked."""
    if not public_members_store.is_member(chat_id):
        logger.warning("Public cash refused.", extra={"chat_id": chat_id})
        return {"sent": 0, "reason": "not_a_member"}
    try:
        figures = public_cache.get_or_read(_CASH_KEY, _read_public_cash)
        title = _cash_title()
        image = build_cash_image(figures["rows"], title, figures["notes"])
        send_telegram_photo_or_raise(config.TELEGRAM_BOT_TOKEN, chat_id, image, title)
    except Exception:
        logger.exception("Public cash failed.", extra={"chat_id": chat_id})
        return _public_reply_unavailable(chat_id, "Saldos")
    return {"sent": 1}


def _board_since(biwenger, since: float, page: int = 50) -> list[dict]:
    """Board entries newest first, paging only until one is older than `since`."""
    entries: list[dict] = []
    offset = 0
    while True:
        url = f"{config.LEAGUE_BOARD_ALL_URL}&limit={page}&offset={offset}"
        batch = biwenger.get_board_messages(url).get("data") or []
        entries.extend(batch)
        if len(batch) < page or any(e.get("date", 0) < since for e in batch):
            return entries
        offset += page


def _read_public_movements() -> list[dict]:
    biwenger = build_biwenger_session()
    players, _ = BiwengerClient.get_competition_maps(config.ALL_PLAYERS_DATA_URL)
    now = time.time()
    entries = _board_since(biwenger, now - league_cash.MOVEMENTS_WINDOW_S)
    return league_cash.movements(entries, now, players)


def run_public_movements(chat_id: str) -> dict:
    """`/movimientos` for an allowlisted member."""
    if not public_members_store.is_member(chat_id):
        logger.warning("Public movements refused.", extra={"chat_id": chat_id})
        return {"sent": 0, "reason": "not_a_member"}
    try:
        items = public_cache.get_or_read(_MOVEMENTS_KEY, _read_public_movements)
        send_telegram_message_or_raise(
            bot_token=config.TELEGRAM_BOT_TOKEN,
            chat_id=chat_id,
            text=league_cash.render_movements(items),
        )
    except Exception:
        logger.exception("Public movements failed.", extra={"chat_id": chat_id})
        return _public_reply_unavailable(chat_id, "Movimientos")
    return {"sent": 1, "movements": len(items)}


def list_public_managers(chat_id: str) -> dict:
    """The rivals a public chat may analyse: every manager but the owner,
    whose squad and projections are his own edge. Cached like the rest."""
    if not public_members_store.is_member(chat_id):
        return {"managers": []}

    def read() -> list[dict]:
        return [
            {"id": m["id"], "name": m["name"]}
            for m in list_managers()["managers"]
            if not m.get("is_me")
        ]

    return {"managers": public_cache.get_or_read("managers", read)}


def _read_public_team(manager_id: int) -> dict:
    """One rival's squad image, clause columns included, as bytes to cache."""
    ctx = build_context()
    biwenger = ctx.biwenger
    managers = biwenger.get_league_users(
        config.LEAGUE_DATA_URL, config.NON_PLAYING_MEMBER_IDS
    )
    upcoming = read_fixture_runs(biwenger)
    squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, manager_id)
    rows = build_squad_rows(
        squad,
        ctx.biwenger_players,
        ctx.jp_index,
        ctx.oraculo_index,
        include_clause=True,
        oraculo_scale=ctx.oraculo_scale,
    )
    title = f"👤 {managers.get(manager_id, manager_id)}"
    return {"png": _squad_image(rows, title, upcoming, True), "title": title}


def run_public_team(chat_id: str, manager_id: int) -> dict:
    """`/analizar` for a public chat: one rival's squad, sent to that chat.
    The owner's own team is refused however it is asked for."""
    if not public_members_store.is_member(chat_id):
        logger.warning("Public team refused.", extra={"chat_id": chat_id})
        return {"sent": 0, "reason": "not_a_member"}
    try:
        rivals = {m["id"] for m in list_public_managers(chat_id)["managers"]}
        if manager_id not in rivals:
            logger.warning(
                "Public team outside the rivals.",
                extra={"chat_id": chat_id, "manager_id": manager_id},
            )
            return {"sent": 0, "reason": "not_a_rival"}
        image = public_cache.get_or_read(
            f"team:{manager_id}", lambda: _read_public_team(manager_id)
        )
        send_telegram_photo_or_raise(
            config.TELEGRAM_BOT_TOKEN, chat_id, image["png"], image["title"]
        )
    except Exception:
        logger.exception("Public team failed.", extra={"chat_id": chat_id})
        return _public_reply_unavailable(chat_id, "Análisis")
    return {"sent": 1}


def list_public_members() -> dict:
    """The allowlist, each id labelled: the owner's own name for him if he
    gave one, else the manager he registered as in the draft."""
    members = public_members_store.load()
    names: dict[int, str] = {}
    try:
        names.update(draft_names_by_telegram_id())
    except Exception:
        logger.warning("Draft registry unreadable — members go unnamed.")
    names.update(public_members_store.load_names())
    return {
        "members": sorted(members),
        "names": {str(m): names[m] for m in sorted(members) if m in names},
        "pending": {
            str(c): title for c, title in public_members_store.load_pending().items()
        },
    }


def check_public_chat(chat_id: str, title: str) -> dict:
    """The bot's gate. A chat that is not a member is remembered, unanswered,
    so the owner can authorize it from `/publico`."""
    if public_members_store.is_member(chat_id):
        return {"allowed": True}
    try:
        public_members_store.remember_pending(int(chat_id), title)
    except (TypeError, ValueError):
        pass
    return {"allowed": False}


def edit_public_members(user_id: int, action: str, name: str | None = None) -> dict:
    if action == "add":
        public_members_store.add(user_id, name)
    else:
        public_members_store.remove(user_id)
    return list_public_members()


def run_protection_watch(ctx) -> dict:
    """Warn when one of the owner's players stops being clause-protected within
    a day and some rival could pay the clause. Chained into the daily digest.

    A quiet morning costs one squad read: the board and the rival squads are
    only read once a lock is actually ending.
    """
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    biwenger = ctx.biwenger
    mine = _my_clause_rows(
        ctx, biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
    )
    ending = league_cash.protection_ending(mine, time.time(), _PROTECTION_WINDOW_S)
    if not ending:
        return {"ending": 0, "sent": 0}

    money, _, _, _, _ = _league_money(biwenger, ctx.biwenger_players)
    starters = trader.best_eleven_ids(mine) or None
    text = league_cash.protection_alert(ending, _rivals(money), starters)
    if text:
        send_telegram_message_or_raise(bot_token=token, chat_id=chat_id, text=text)
    logger.info(
        "Protection watch ran.",
        extra={"ending": len(ending), "sent": bool(text)},
    )
    return {"ending": len(ending), "sent": int(bool(text))}


# Enough open rounds to give every team its next `GAMES_AHEAD` games: a
# postponed round holds a single fixture, so one round is not one game each.
_FIXTURE_ROUNDS_MAX = fixture_run.GAMES_AHEAD + 2


def read_open_rounds(biwenger) -> list[dict] | None:
    """The current round plus the season's open ones, or `None` when the
    calendar could not be read. Sequential public reads on the cf host.

    Never raises: what it feeds — a market image's fixture column, the
    trader's round-eve check — must degrade to "calendar unknown", not fail.
    """
    try:
        current = biwenger.get_round()
        if not current:
            return None
        rounds = [current]
        for round_id in fixture_run.rounds_to_read(current)[:_FIXTURE_ROUNDS_MAX]:
            if round_id != current.get("id"):
                rounds.append(biwenger.get_round(round_id))
        return rounds
    except Exception:
        logger.exception("Fixture calendar unreadable — going without it.")
        return None


def read_fixture_runs(biwenger) -> dict | None:
    """`{team_id: [difficulty, …]}` for the games ahead, or `None` when the
    calendar could not be read."""
    rounds = read_open_rounds(biwenger)
    return None if rounds is None else fixture_run.upcoming_by_team(rounds, time.time())


def _market_image(rows: list[dict], title: str, upcoming: dict | None) -> bytes:
    column = fixture_run.annotate(rows, upcoming)
    return build_table_image(rows, title, extra_cols=[column])


def _squad_image(
    rows: list[dict], title: str, upcoming: dict | None, clauses: bool
) -> bytes:
    """A squad table with its total value, the fixture column, and — for a
    rival — the clause columns before it."""
    column = fixture_run.annotate(rows, upcoming)
    extra = (["Clausulable", "Cláusula"] if clauses else []) + [column]
    return build_table_image(rows, title, extra_cols=extra, show_total_value=True)


def _round_context(biwenger) -> "round_context.RoundContext":
    """Where the season is. Never raises — it decorates a message, and losing
    the lineup because the calendar could not be read is the wrong trade."""
    try:
        return round_context.read(biwenger.get_round())
    except Exception:
        logger.exception("Could not read the round — message goes without it.")
        return round_context.RoundContext()


def _diff_against_saved_lineup(biwenger, result: dict, my_team: list) -> dict:
    """Compare the optimum against what is set on Biwenger. Never raises.

    A failed read must not cost the preview: it degrades to "could not
    compare" and the optimal eleven still goes out, the way `/ofertas` stands
    its depth signal down rather than failing the inbox.
    """
    try:
        current = biwenger.get_current_lineup()
    except Exception:
        logger.exception("Could not read the saved lineup — previewing without it.")
        return lineup_logic._not_comparable(
            "No se ha podido leer tu alineación actual para compararla."
        )
    return lineup_logic.diff_against_current(result, my_team, current)


def run_auto_pick_lineup(dry_run: bool = False, ctx=None) -> dict:
    """Pick the best lineup, apply it on Biwenger, confirm via Telegram.

    Used by POST /lineups/auto-pick (was /alinear). With `dry_run=True`
    skips the Biwenger PUT and sends the would-be lineup to Telegram as
    a preview — useful before a high-stakes matchday.

    `ctx` lets the daily digest hand over the context it already built, so
    chaining this step costs no extra JP + Biwenger round-trip.
    """
    ctx = ctx or build_context()
    # Before anything reaches Biwenger: a failure applying the lineup must not
    # cost the record of what was projected.
    projection_ledger_capture.capture(ctx)
    projection_ledger_capture.collect(ctx)
    biwenger, biwenger_players, jp_index, oraculo_index, oraculo_scale = (
        ctx.biwenger,
        ctx.biwenger_players,
        ctx.jp_index,
        ctx.oraculo_index,
        ctx.oraculo_scale,
    )
    telegram = require_telegram()
    if telegram is None:
        return {"sent": 0, "reason": "telegram_credentials_missing"}
    token, chat_id = telegram

    my_squad = biwenger.get_manager_squad(config.USER_SQUAD_URL, biwenger.user_id)
    my_team = build_squad_rows(
        my_squad, biwenger_players, jp_index, oraculo_index, oraculo_scale=oraculo_scale
    )

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
        diff = _diff_against_saved_lineup(biwenger, result, my_team)
        preview = format_preview_message(result, diff, my_team)
        header = round_context.format_line(_round_context(biwenger))
        if header:
            preview = f"{header}\n\n{preview}"
        send_telegram_message_or_raise(bot_token=token, chat_id=chat_id, text=preview)
        logger.info(
            "Dry-run lineup preview sent.",
            extra={
                "formation": result["formation"],
                "total_sf": result["total_sf"],
                "comparable": diff["comparable"],
                "identical": diff["identical"],
                "delta": diff["delta"],
            },
        )
        return {
            "sent": 1,
            "applied": False,
            "dry_run": True,
            "formation": result["formation"],
            "total_sf": result["total_sf"],
            "identical": diff["identical"],
            "delta": diff["delta"],
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

    applied = format_lineup_message(result)
    header = round_context.format_line(_round_context(biwenger))
    if header:
        applied = f"{header}\n\n{applied}"
    send_telegram_message_or_raise(bot_token=token, chat_id=chat_id, text=applied)
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
