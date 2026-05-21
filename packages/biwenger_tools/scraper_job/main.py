"""Scraper job: fetch Biwenger messages and dual-write CSV + Firestore.

CSVs are uploaded to Google Drive (legacy path, served when
``DATA_BACKEND=csv``) and the same data is mirrored into Firestore
(read by the web when ``DATA_BACKEND=firestore``). After the flag flip
and cleanup PR, the CSV path goes away.
"""

import csv
import hashlib
import io
import os
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

from core.constants import MADRID_TZ
from core.domain.models import Clausulazo, JusticeEntry, LeagueMessage, Participation
from core.sdk import firestore
from core.sdk.biwenger import BiwengerClient
from core.sdk.gcp import (
    download_csv_as_dict,
    find_file_on_drive,
    get_google_service,
    upload_csv_to_drive,
)
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


def _read_credentials(cfg) -> tuple[str, str, str]:
    """Read Biwenger and Drive credentials from environment variables."""
    email = cfg.BIWENGER_EMAIL
    password = cfg.BIWENGER_PASSWORD
    folder_id = cfg.GDRIVE_FOLDER_ID
    if not all([email, password, folder_id]):
        raise ValueError("No se pudieron leer todas las credenciales necesarias.")
    return email, password, folder_id


def _init_drive_service(cfg):
    """Initialize and return the Google Drive service."""
    sa_path = cfg.SERVICE_ACCOUNT_PATH
    if not os.path.exists(sa_path):
        sa_path = os.path.join(os.path.dirname(__file__), "biwenger-tools-sa.json")
    return get_google_service("drive", "v3", sa_path, cfg.SCOPES)


def _get_existing_comunicados(
    drive_service, filename: str, folder_id: str
) -> tuple[list, set, Optional[str]]:
    """Download existing comunicados CSV from Drive.

    Returns (messages, existing_id_hashes, file_id).
    """
    file_meta = find_file_on_drive(drive_service, filename, folder_id)
    if file_meta:
        rows = download_csv_as_dict(drive_service, file_meta["id"])
        messages = [LeagueMessage.from_csv_row(r) for r in rows]
        return messages, {m.id_hash for m in messages}, file_meta["id"]
    logger.info(
        "CSV not found in Drive — will be created.", extra={"file_name": filename}
    )
    return [], set(), None


def _process_new_messages(
    board_messages: list, existing_ids: set, user_map: dict
) -> list:
    """Parse board messages and return only those not already stored."""
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


def _write_and_upload_csv(
    drive_service,
    folder_id: str,
    filename: str,
    model_cls,
    models: list,
    existing_file_id: Optional[str],
) -> None:
    """Serialize a list of domain models to CSV and upload to Drive."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(model_cls.CSV_FIELDS))
    writer.writeheader()
    writer.writerows(m.to_csv_row() for m in models)
    upload_csv_to_drive(
        drive_service, folder_id, filename, buf.getvalue(), existing_file_id
    )


def _clausulazo_doc_id(c: Clausulazo) -> str:
    """Deterministic Firestore doc id for a clausulazo — content hash.

    Must match ``scripts/backfill_firestore.py::_clausulazo_id`` so the
    scraper and the one-shot backfill produce identical doc ids for the
    same transfer.
    """
    raw = "|".join(
        str(v)
        for v in (c.fecha, c.jugador, c.equipo_vendedor, c.equipo_comprador, c.precio)
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _write_to_firestore(collection: str, pairs: list[tuple[str, dict]]) -> None:
    """Wipe + bulk-write a Firestore collection.

    Mirrors the CSV-overwrite semantics: every scraper run reflects the
    full latest state, so deletions on Biwenger propagate (a board message
    removed upstream disappears from Firestore on the next run).
    """
    deleted = firestore.delete_collection(collection)
    written = firestore.batch_write(collection, pairs)
    logger.info(
        "Firestore collection rewritten.",
        extra={"collection": collection, "deleted": deleted, "written": written},
    )


def _upload_clausulazos(
    drive_service, biwenger: BiwengerClient, cfg, folder_id: str
) -> None:
    """Download, parse, and upload clausulazos and tabla_justicia CSVs."""
    logger.info("Processing clausulazos...")
    players_map = biwenger.get_all_players_data_map(cfg.ALL_PLAYERS_DATA_URL)
    raw = biwenger.get_all_clausulazos(cfg.CLAUSULAZOS_URL)
    clausulazos = parse_clausulazos(raw, players_map)
    tabla_justicia = build_tabla_justicia(clausulazos)
    logger.info("Clausulazos processed.", extra={"count": len(clausulazos)})

    season = cfg.TEMPORADA_ACTUAL
    clausulazos_filename = f"{cfg.CLAUSULAZOS_FILENAME_BASE}_{season}.csv"
    clausulazos_meta = find_file_on_drive(
        drive_service, clausulazos_filename, folder_id
    )
    _write_and_upload_csv(
        drive_service,
        folder_id,
        clausulazos_filename,
        Clausulazo,
        clausulazos,
        clausulazos_meta["id"] if clausulazos_meta else None,
    )
    _write_to_firestore(
        f"clausulazos/{season}/transfers",
        [(_clausulazo_doc_id(c), c.to_firestore()) for c in clausulazos],
    )

    tabla_filename = f"{cfg.TABLA_JUSTICIA_FILENAME_BASE}_{season}.csv"
    tabla_meta = find_file_on_drive(drive_service, tabla_filename, folder_id)
    _write_and_upload_csv(
        drive_service,
        folder_id,
        tabla_filename,
        JusticeEntry,
        tabla_justicia,
        tabla_meta["id"] if tabla_meta else None,
    )
    _write_to_firestore(
        f"tabla_justicia/{season}/teams",
        [(e.equipo, e.to_firestore()) for e in tabla_justicia if e.equipo],
    )
    logger.info("Clausulazos and tabla_justicia written to CSV + Firestore.")


def _notify(text: str) -> None:
    """Send a Telegram message to the configured chat. No-op without creds.

    Notification failures are swallowed — they should never mask the
    scraper result. The Telegram SDK already logs its own errors.
    """
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        logger.warning("Telegram creds missing — skipping scraper notify.")
        return
    send_telegram_message(
        bot_token=config.TELEGRAM_BOT_TOKEN,
        chat_id=config.TELEGRAM_CHAT_ID,
        text=text,
    )


def main() -> None:
    """Orchestrate message scraping, processing, and Drive upload.

    Sends a Telegram message to the configured chat at the end (success or
    failure). On failure, re-raises so Cloud Run marks the execution as
    failed — silent failure used to leave dead executions looking green.
    """
    started_at = datetime.now(timezone.utc)
    new_count = 0

    try:
        logger.info("Scraper started.", extra={"temporada": config.TEMPORADA_ACTUAL})

        email, password, folder_id = _read_credentials(config)
        drive_service = _init_drive_service(config)
        biwenger = BiwengerClient(
            email, password, config.LOGIN_URL, config.ACCOUNT_URL, config.LEAGUE_ID
        )

        comunicados_filename = f"comunicados_{config.TEMPORADA_ACTUAL}.csv"
        all_messages, existing_ids, existing_file_id = _get_existing_comunicados(
            drive_service, comunicados_filename, folder_id
        )

        board_messages = biwenger.get_all_board_messages(config.BOARD_MESSAGES_URL)
        logger.info("Board messages downloaded.", extra={"count": len(board_messages)})
        user_map = biwenger.get_league_users(config.LEAGUE_USERS_URL)

        new_messages = _process_new_messages(board_messages, existing_ids, user_map)
        new_count = len(new_messages)
        if new_messages:
            logger.info("New messages found.", extra={"count": new_count})
            season = config.TEMPORADA_ACTUAL
            all_messages = sort_messages(all_messages + new_messages)
            _write_and_upload_csv(
                drive_service,
                folder_id,
                comunicados_filename,
                LeagueMessage,
                all_messages,
                existing_file_id,
            )
            _write_to_firestore(
                f"comunicados/{season}/messages",
                [(m.id_hash, m.to_firestore()) for m in all_messages if m.id_hash],
            )
            participacion_filename = f"participacion_{season}.csv"
            part_meta = find_file_on_drive(
                drive_service, participacion_filename, folder_id
            )
            participaciones = process_participation(all_messages, user_map)
            _write_and_upload_csv(
                drive_service,
                folder_id,
                participacion_filename,
                Participation,
                participaciones,
                part_meta["id"] if part_meta else None,
            )
            _write_to_firestore(
                f"participacion/{season}/authors",
                [(p.autor, p.to_firestore()) for p in participaciones if p.autor],
            )
        else:
            logger.info("No new messages found.")

        _upload_clausulazos(drive_service, biwenger, config, folder_id)

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
        body = f"🧹 <b>Scraper OK</b> · {new_count} mensajes nuevos · {elapsed:.0f}s"
    else:
        body = f"🧹 <b>Scraper OK</b> · sin mensajes nuevos · {elapsed:.0f}s"
    _notify(body)


if __name__ == "__main__":
    main()
