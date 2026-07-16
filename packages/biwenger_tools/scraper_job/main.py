"""Scraper job: fetch Biwenger board messages and write them to Firestore.

Every run is idempotent — `comunicados/{season}/messages` is keyed by a
content hash, and `participacion`, `clausulazos`, `tabla_justicia` are
rewritten in full (wipe + bulk-write) so a deletion upstream propagates.
"""

import hashlib
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from core.constants import MADRID_TZ
from core.domain.models import Clausulazo, LeagueMessage
from core.sdk import firestore
from core.sdk.biwenger import BiwengerClient
from core.sdk.telegram import send_telegram_message
from core.utils import get_logger
from packages.biwenger_tools.scraper_job import config
from packages.biwenger_tools.scraper_job.logic.processing import (
    build_tabla_justicia,
    categorize_title,
    parse_clausulazos,
    process_participation,
    sort_messages,
)

logger = get_logger(__name__)


def _read_credentials(cfg) -> tuple[str, str]:
    """Read Biwenger credentials from environment / Secret Manager."""
    email = cfg.BIWENGER_EMAIL
    password = cfg.BIWENGER_PASSWORD
    if not all([email, password]):
        raise ValueError("Missing Biwenger credentials (email/password).")
    return email, password


def _existing_message_ids(season: str) -> set[str]:
    """Return the set of `id_hash`es already stored for the season.

    Used as the dedupe filter when processing fresh board messages —
    cheaper than reading full documents because Firestore streams just
    the doc references.
    """
    collection = firestore.get_client().collection(f"comunicados/{season}/messages")
    # `select([])` asks Firestore for empty projections, so each snap only
    # carries its id over the wire — minimum cost for the dedupe lookup.
    return {snap.id for snap in collection.select([]).stream()}


def _existing_messages(season: str) -> list[LeagueMessage]:
    """All current `LeagueMessage`s for the season, used to recompute
    derived collections (participacion) after appending the new ones."""
    return [
        LeagueMessage.from_firestore(doc_id, data)
        for doc_id, data in firestore.list_documents(f"comunicados/{season}/messages")
    ]


def _process_new_messages(
    board_messages: list, existing_ids: set, user_map: dict
) -> list:
    """Parse raw board entries and return only those not already stored."""
    new_messages: list[LeagueMessage] = []
    for item in board_messages:
        content_html = item.get("content", "")
        content_text = BeautifulSoup(content_html, "html.parser").get_text(
            separator=" ", strip=True
        )
        id_hash = hashlib.sha256(
            f"{item.get('date', '')}{content_text}".encode("utf-8")
        ).hexdigest()
        if id_hash in existing_ids:
            continue
        author = item.get("author")
        author_id = author.get("id") if author else None
        fecha = datetime.fromtimestamp(item["date"], tz=timezone.utc).astimezone(
            MADRID_TZ
        )
        title = item.get("title", "Sin título")
        new_messages.append(
            LeagueMessage(
                id_hash=id_hash,
                fecha=fecha.strftime("%d-%m-%Y %H:%M:%S"),
                autor=user_map.get(author_id, "Autor Desconocido"),
                titulo=title,
                contenido=content_html,
                categoria=categorize_title(title),
            )
        )
    return new_messages


def _clausulazo_doc_id(c: Clausulazo) -> str:
    """Deterministic Firestore doc id for a clausulazo — content hash so
    re-running the scraper rewrites the same document instead of creating
    duplicates."""
    raw = "|".join(
        str(v)
        for v in (c.fecha, c.jugador, c.equipo_vendedor, c.equipo_comprador, c.precio)
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _write_collection(collection: str, pairs: list[tuple[str, dict]]) -> None:
    """Wipe + bulk-write a Firestore collection.

    Matches the contract the backfill script uses, so deletions on
    Biwenger propagate (a board message removed upstream disappears from
    Firestore on the next run).
    """
    deleted = firestore.delete_collection(collection)
    written = firestore.batch_write(collection, pairs)
    logger.info(
        "Firestore collection rewritten.",
        extra={"collection": collection, "deleted": deleted, "written": written},
    )


def _existing_clausulazo_ids(season: str) -> set[str]:
    """Doc ids of clausulazos already in Firestore for the season."""
    collection = firestore.get_client().collection(f"clausulazos/{season}/transfers")
    return {snap.id for snap in collection.select([]).stream()}


def _write_clausulazos_and_tabla(biwenger: BiwengerClient, cfg) -> int:
    """Pull the clausulazos feed, derive the justice table, write both.

    Returns the number of clausulazos that did not exist in Firestore
    before this run (i.e. new since the last scraper execution).
    """
    logger.info("Processing clausulazos...")
    players_map = biwenger.get_all_players_data_map(cfg.ALL_PLAYERS_DATA_URL)
    raw = biwenger.get_all_clausulazos(cfg.CLAUSULAZOS_URL)
    clausulazos = parse_clausulazos(raw, players_map)
    tabla_justicia = build_tabla_justicia(clausulazos)

    season = cfg.TEMPORADA_ACTUAL
    existing_ids = _existing_clausulazo_ids(season)
    new_count = sum(1 for c in clausulazos if _clausulazo_doc_id(c) not in existing_ids)
    logger.info(
        "Clausulazos processed.",
        extra={"total": len(clausulazos), "new": new_count},
    )

    _write_collection(
        f"clausulazos/{season}/transfers",
        [(_clausulazo_doc_id(c), c.to_firestore()) for c in clausulazos],
    )
    _write_collection(
        f"tabla_justicia/{season}/teams",
        [(e.equipo, e.to_firestore()) for e in tabla_justicia if e.equipo],
    )
    logger.info("Clausulazos and tabla_justicia written to Firestore.")
    return new_count


def _notify(text: str) -> None:
    """Send a Telegram message to the configured chat. No-op without creds."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        logger.warning("Telegram creds missing — skipping scraper notify.")
        return
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text=text,
    )


def main() -> None:
    """Pull board messages, write everything to Firestore, notify Telegram.

    Sends a Telegram message at the end (success or failure). On error
    re-raises so Cloud Run marks the execution as failed — silent
    failure used to leave dead executions looking green.
    """
    started_at = datetime.now(timezone.utc)
    new_count = 0
    clausulazos_count = 0

    try:
        season = config.TEMPORADA_ACTUAL
        logger.info("Scraper started.", extra={"temporada": season})

        email, password = _read_credentials(config)
        biwenger = BiwengerClient(
            email, password, config.LOGIN_URL, config.ACCOUNT_URL, config.LEAGUE_ID
        )

        board_messages = biwenger.get_all_board_messages(config.BOARD_MESSAGES_URL)
        logger.info("Board messages downloaded.", extra={"count": len(board_messages)})
        # include_non_playing: the cronista's messages must resolve an author
        # and count in participación, even though they never compete.
        user_map = biwenger.get_league_users(
            config.LEAGUE_USERS_URL, include_non_playing=True
        )

        new_messages = _process_new_messages(
            board_messages, _existing_message_ids(season), user_map
        )
        new_count = len(new_messages)
        if new_messages:
            logger.info("New messages found.", extra={"count": new_count})
            all_messages = sort_messages(_existing_messages(season) + new_messages)
            _write_collection(
                f"comunicados/{season}/messages",
                [(m.id_hash, m.to_firestore()) for m in all_messages if m.id_hash],
            )
            participaciones = process_participation(all_messages, user_map)
            _write_collection(
                f"participacion/{season}/authors",
                [(p.autor, p.to_firestore()) for p in participaciones if p.autor],
            )
        else:
            logger.info("No new messages found.")

        clausulazos_count = _write_clausulazos_and_tabla(biwenger, config)

    except Exception as exc:
        logger.exception("Unexpected error in scraper.")
        elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
        _notify(
            "❌ <b>Scraper falló</b>\n"
            f"<code>{type(exc).__name__}: {exc}</code>\n"
            f"⏱️ {elapsed:.0f}s · ver logs en Cloud Run"
        )
        raise  # let Cloud Run mark the execution as failed

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    if new_count > 0:
        msg_s = "s" if new_count != 1 else ""
        messages_part = f"{new_count} mensaje{msg_s} nuevo{msg_s}"
    else:
        messages_part = "sin mensajes nuevos"
    if clausulazos_count > 0:
        cl_s = "s" if clausulazos_count != 1 else ""
        clausulazos_part = f"{clausulazos_count} clausulazo{cl_s} nuevo{cl_s}"
    else:
        clausulazos_part = "sin clausulazos nuevos"
    body = (
        f"🧹 <b>Scraper OK</b> · {messages_part} · "
        f"{clausulazos_part} · {elapsed:.0f}s"
    )
    _notify(body)


if __name__ == "__main__":
    main()
