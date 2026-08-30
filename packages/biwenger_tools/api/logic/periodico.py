"""Publish a league newspaper front page from a Telegram attachment.

The web resolves front pages straight off a public bucket — it reads
`periodico/{season}/index.json` and builds each image URL as `{fecha}.jpg`
(`packages/biwenger_tools/web/routes/season.py`). So publishing is two object
writes and no deploy; this module is what turns a photo sent to the bot into
those two writes.

The date is not decoration: it is the object name and the manifest key, which
is why one date holds exactly one front page and re-sending replaces it.
"""

import json
import re
from datetime import datetime

import requests

from core.constants import MADRID_TZ
from core.sdk.gcp import download_object, upload_object
from core.sdk.telegram import download_telegram_file
from core.utils import get_logger
from packages.biwenger_tools.api import config

logger = get_logger(__name__)

_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*[-|—]?\s*(.*)$", re.DOTALL)

# JPEG only. `_fetch_portadas` hardcodes the `.jpg` extension, so storing a PNG
# under that name would leave bytes, content type and extension disagreeing.
_JPEG_MAGIC = b"\xff\xd8\xff"

# The manifest changes in place, so it must not sit in the edge cache for the
# default hour — the web adds its own 600 s TTL on top. The images never change
# under a given date and keep the default.
_MANIFEST_CACHE_CONTROL = "public, max-age=60"

_HELP = (
    "Mándala otra vez con un pie de foto: "
    "<code>Titular</code>, o <code>2026-08-14 Titular</code> "
    "para publicarla con otra fecha."
)


class PortadaRejected(Exception):
    """The request is unusable as sent — the operator has to resend it.

    Distinct from a failure: the caller answers 200 with the message so the
    bot relays plain instructions instead of an error trace.
    """


def _today_madrid() -> str:
    return datetime.now(MADRID_TZ).strftime("%Y-%m-%d")


def parse_caption(caption: str) -> tuple[str, str]:
    """Split a caption into `(fecha, titulo)`.

    An explicit `YYYY-MM-DD` prefix wins; without one the front page is
    published under today's date in Madrid. Raises `PortadaRejected` when
    there is no title left — an empty one renders a blank card on the web.
    """
    caption = (caption or "").strip()
    if not caption:
        raise PortadaRejected(f"❌ La portada necesita un titular.\n\n{_HELP}")

    match = _DATE_PREFIX.match(caption)
    if match:
        fecha, titulo = match.group(1), match.group(2).strip()
        try:
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            raise PortadaRejected(
                f"❌ <code>{fecha}</code> no es una fecha válida.\n\n{_HELP}"
            )
    else:
        fecha, titulo = _today_madrid(), caption

    if not titulo:
        raise PortadaRejected(f"❌ La portada necesita un titular.\n\n{_HELP}")
    return fecha, titulo


def _upsert(entries: list, fecha: str, titulo: str) -> list:
    """Manifest with `fecha` set to `titulo`, newest first.

    Replaces rather than appends: the same date twice would otherwise render
    two cards pointing at the one image that survived the overwrite.
    """
    kept = [e for e in entries if e.get("fecha") != fecha]
    kept.append({"fecha": fecha, "titulo": titulo})
    return sorted(kept, key=lambda e: e["fecha"], reverse=True)


def _read_manifest(bucket: str, path: str) -> list:
    """Current manifest, or `[]` for a season that has published none.

    A manifest that exists but does not parse is left alone — overwriting it
    with a single entry would drop every front page of the season.
    """
    raw = download_object(bucket, path)
    if raw is None:
        return []
    try:
        entries = json.loads(raw)
    except ValueError:
        raise RuntimeError(f"{path} is not valid JSON — refusing to overwrite it")
    if not isinstance(entries, list):
        raise RuntimeError(f"{path} is not a JSON list — refusing to overwrite it")
    return entries


def publish_portada(file_id: str, caption: str, kind: str) -> dict:
    """Publish the attachment as the front page for its date.

    Returns `{"message": ...}` ready for the bot to relay — including the
    rejection cases, which are the operator's to fix and not failures. Raises
    on anything that is genuinely broken (Telegram unreachable, no write
    access to the bucket) so the caller reports an error.
    """
    season = config.CURRENT_SEASON
    bucket = config.PERIODICO_BUCKET

    try:
        fecha, titulo = parse_caption(caption)
    except PortadaRejected as exc:
        return {"published": False, "message": str(exc)}

    try:
        image = download_telegram_file(config.TELEGRAM_BOT_TOKEN, file_id)
    except requests.RequestException as exc:
        logger.warning("Portada download failed.", extra={"error": str(exc)})
        return {
            "published": False,
            "message": (
                "❌ No he podido descargar la imagen de Telegram. "
                "Si pesa más de 20 MB mándala comprimida o baja la resolución."
            ),
        }

    if not image.startswith(_JPEG_MAGIC):
        return {
            "published": False,
            "message": (
                "❌ La portada tiene que ser un JPEG — la web las publica "
                "como <code>.jpg</code>. Expórtala en ese formato y reenvíala."
            ),
        }

    image_path = f"periodico/{season}/{fecha}.jpg"
    manifest_path = f"periodico/{season}/index.json"

    entries = _read_manifest(bucket, manifest_path)
    replaced = any(e.get("fecha") == fecha for e in entries)

    url = upload_object(bucket, image_path, image, "image/jpeg")
    upload_object(
        bucket,
        manifest_path,
        json.dumps(
            _upsert(entries, fecha, titulo), ensure_ascii=False, indent=2
        ).encode("utf-8"),
        "application/json",
        cache_control=_MANIFEST_CACHE_CONTROL,
    )

    logger.info(
        "Portada published.",
        extra={
            "season": season,
            "fecha": fecha,
            "kind": kind,
            "replaced": replaced,
            "bytes": len(image),
        },
    )

    quality = (
        ""
        if kind == "document"
        else (
            "\n\n<i>Telegram recomprime las fotos: mándala como archivo "
            "si quieres que se lea la letra pequeña.</i>"
        )
    )
    return {
        "published": True,
        "fecha": fecha,
        "titulo": titulo,
        "url": url,
        "replaced": replaced,
        "message": (
            f"📰 <b>Portada {'actualizada' if replaced else 'publicada'}</b>\n\n"
            f"{titulo}\n{fecha}\n\n"
            f"{url}{quality}"
        ),
    }
