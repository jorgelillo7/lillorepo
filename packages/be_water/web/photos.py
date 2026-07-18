"""Bottle photo handling: normalization + GCS storage via REST.

Uploads use the JSON API with an ADC token (google-auth is already in the
lock; google-cloud-storage would be a new dependency for three calls).
Images are re-encoded with Pillow before upload, which drops EXIF —
phone photos carry GPS and this bucket is public.
"""

import io

import google.auth
import google.auth.transport.requests
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from core.sdk import gemini
from core.utils import get_logger
from packages.be_water.web import config

logger = get_logger(__name__)

_STORAGE_API = "https://storage.googleapis.com"
MAX_SIDE = 1200
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # refuse absurd uploads before Pillow

STUDIO_SIZE = 1080  # square, timeline-friendly
WATERMARK = "💧 Be Water · Jorge Lillo"
_STUDIO_PROMPT = (
    "Aísla la botella de agua de esta foto y colócala perfectamente vertical, "
    "centrada, sobre un fondo blanco puro uniforme, estilo fotografía de "
    "producto de estudio. Conserva la botella y su etiqueta tal cual son, "
    "sin inventar ni retocar texto. Devuelve solo la imagen."
)


def public_url(object_name: str) -> str:
    return f"{_STORAGE_API}/{config.PHOTOS_BUCKET}/{object_name}"


def process_image(data: bytes) -> bytes:
    """Upright, ≤1200px, JPEG, EXIF-free."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


def studio_photo(raw_photo: bytes) -> bytes:
    """Bottle shot → product-style studio photo with the brand watermark.

    Nano banana isolates the bottle upright on pure white; Pillow squares
    the canvas and stamps the watermark. Raises on any failure — the
    caller falls back to the raw photo (a kitchen background is worse
    than no studio, but better than losing the add flow).
    """
    cutout = gemini.generate_image(
        api_key=config.GEMINI_API_KEY,
        prompt=_STUDIO_PROMPT,
        image_bytes=raw_photo,
        model=config.GEMINI_IMAGE_MODEL,
    )
    img = Image.open(io.BytesIO(cutout)).convert("RGB")
    img.thumbnail((int(STUDIO_SIZE * 0.86), int(STUDIO_SIZE * 0.86)))

    canvas = Image.new("RGB", (STUDIO_SIZE, STUDIO_SIZE), "white")
    canvas.paste(img, ((STUDIO_SIZE - img.width) // 2, (STUDIO_SIZE - img.height) // 2))

    draw = ImageDraw.Draw(canvas, "RGBA")
    try:
        font = ImageFont.load_default(size=28)
    except TypeError:  # pragma: no cover — Pillow < 10.1 fallback
        font = ImageFont.load_default()
    text = WATERMARK
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (STUDIO_SIZE - (box[2] - box[0]) - 28, STUDIO_SIZE - (box[3] - box[1]) - 24),
        text,
        font=font,
        fill=(100, 116, 139, 160),  # slate-500 semi-transparent
    )

    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue()


def _auth_header() -> dict:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/devstorage.read_write"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return {"Authorization": f"Bearer {credentials.token}"}


def upload_photo(object_name: str, data: bytes) -> str:
    """Upload JPEG bytes; returns the public URL."""
    response = requests.post(
        f"{_STORAGE_API}/upload/storage/v1/b/{config.PHOTOS_BUCKET}/o",
        params={"uploadType": "media", "name": object_name},
        headers={**_auth_header(), "Content-Type": "image/jpeg"},
        data=data,
        timeout=30,
    )
    response.raise_for_status()
    logger.info("Photo uploaded.", extra={"object": object_name, "bytes": len(data)})
    return public_url(object_name)


def promote_photo(tmp_name: str, final_name: str) -> str:
    """Server-side copy tmp → final, best-effort delete of tmp."""
    headers = _auth_header()
    response = requests.post(
        f"{_STORAGE_API}/storage/v1/b/{config.PHOTOS_BUCKET}/o/"
        f"{requests.utils.quote(tmp_name, safe='')}/copyTo/b/"
        f"{config.PHOTOS_BUCKET}/o/{requests.utils.quote(final_name, safe='')}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    try:
        requests.delete(
            f"{_STORAGE_API}/storage/v1/b/{config.PHOTOS_BUCKET}/o/"
            f"{requests.utils.quote(tmp_name, safe='')}",
            headers=headers,
            timeout=15,
        )
    except requests.RequestException:  # pragma: no cover — dust, not a failure
        logger.warning("Tmp photo cleanup failed.", extra={"object": tmp_name})
    return public_url(final_name)
