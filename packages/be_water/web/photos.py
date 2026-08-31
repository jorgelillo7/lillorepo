"""Bottle photo handling: normalization + GCS storage via REST.

Uploads use the JSON API with an ADC token (google-auth is already in the
lock; google-cloud-storage would be a new dependency for three calls).
Images are re-encoded with Pillow before upload, which drops EXIF —
phone photos carry GPS and this bucket is public.
"""

import io
from collections import Counter

import google.auth
import google.auth.transport.requests
import requests
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from core.sdk import gemini
from core.sdk.gcp import upload_object
from core.utils import get_logger
from packages.be_water.web import config

logger = get_logger(__name__)

_STORAGE_API = "https://storage.googleapis.com"
MAX_SIDE = 1200
MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # refuse absurd uploads before Pillow

STUDIO_SIZE = 1080  # square, timeline-friendly
# No emoji here: PIL's default font has no emoji glyphs (the 💧 silently
# vanished from the first studio photo) — the droplet is drawn as a vector.
WATERMARK = "Be Water · Jorge Lillo"
_STUDIO_PROMPT = (
    "Aísla la botella de agua de esta foto y colócala perfectamente vertical, "
    "centrada, sobre un fondo blanco puro uniforme, estilo fotografía de "
    "producto de estudio. Conserva la botella y su etiqueta tal cual son, "
    "sin inventar ni retocar texto. Devuelve solo la imagen."
)


# How far a pixel may sit from the detected backdrop and still count as part
# of it. Wide enough for the gradient a studio backdrop carries, narrow enough
# to leave a bottle's own highlights alone.
_BACKDROP_TOLERANCE = 15
# Below this the backdrop is a deliberate dark or coloured one, not a white
# that drifted, and flattening it would rewrite the photo rather than fix it.
_BACKDROP_MIN_CHANNEL = 200


def _flatten_backdrop(img: Image.Image) -> Image.Image:
    """Force a near-white backdrop to pure white.

    The prompt asks for pure white and the model does not always deliver it: it
    returns the bottle on its own light-grey studio sweep, which the square
    canvas then frames as a visible grey rectangle — one ficha looking unlike
    every other in the grid. Detected from the border rather than assumed, and
    left alone when the backdrop is genuinely dark or coloured.
    """
    width, height = img.size
    border = [img.getpixel((x, int(height * 0.06))) for x in range(0, width, 7)]
    border += [img.getpixel((int(width * 0.04), y)) for y in range(0, height, 7)]
    backdrop = Counter(border).most_common(1)[0][0]
    if backdrop == (255, 255, 255) or min(backdrop) < _BACKDROP_MIN_CHANNEL:
        return img
    distance = ImageChops.difference(img, Image.new("RGB", img.size, backdrop)).convert(
        "L"
    )
    mask = distance.point(lambda v: 255 if v <= _BACKDROP_TOLERANCE else 0)
    img.paste((255, 255, 255), mask=mask.convert("1"))
    return img


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
        fallback_api_key=config.GEMINI_API_KEY_PAID,
        # 90 s (the default) is not enough once the free allowance is gone: the
        # request is then made twice, and the paid attempt starts after the
        # first has already burned its round trip. The add flow allows the
        # worker 240 s and runs this beside the OCR, so waiting is affordable.
        timeout=180,
        # The image model answers 503 "experiencing high demand" often enough
        # that a single attempt loses the studio photo on a busy morning. The
        # caller degrades to the raw shot either way, so the cost of trying
        # again is latency the add flow already budgets for.
        retries=2,
    )
    img = _flatten_backdrop(Image.open(io.BytesIO(cutout)).convert("RGB"))
    img.thumbnail((int(STUDIO_SIZE * 0.86), int(STUDIO_SIZE * 0.86)))

    canvas = Image.new("RGB", (STUDIO_SIZE, STUDIO_SIZE), "white")
    canvas.paste(img, ((STUDIO_SIZE - img.width) // 2, (STUDIO_SIZE - img.height) // 2))

    _stamp_watermark(canvas)

    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue()


def _stamp_watermark(canvas: Image.Image) -> None:
    """Bottom-right brand mark: vector droplet + text (no emoji fonts)."""
    draw = ImageDraw.Draw(canvas, "RGBA")
    try:
        font = ImageFont.load_default(size=28)
    except TypeError:  # pragma: no cover — Pillow < 10.1 fallback
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), WATERMARK, font=font)
    text_w, text_h = box[2] - box[0], box[3] - box[1]

    drop_h = int(text_h * 1.25)
    drop_w = int(drop_h * 0.72)
    gap = 10
    x_text = canvas.width - text_w - 28
    y_text = canvas.height - text_h - 24
    cx = x_text - gap - drop_w // 2
    cy = y_text + text_h // 2

    # Teardrop: a triangle apex melting into a circle, sky-blue.
    sky = (14, 165, 233, 170)
    r = drop_w // 2
    apex = (cx, cy - drop_h // 2)
    draw.ellipse((cx - r, cy - r // 3, cx + r, cy + drop_h // 2), fill=sky)
    draw.polygon(
        [apex, (cx - int(r * 0.85), cy + r // 4), (cx + int(r * 0.85), cy + r // 4)],
        fill=sky,
    )
    draw.text((x_text, y_text), WATERMARK, font=font, fill=(100, 116, 139, 160))


def _auth_header() -> dict:
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/devstorage.read_write"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return {"Authorization": f"Bearer {credentials.token}"}


# Five minutes, not the bucket's default hour. Every object here is written to
# a stable path and overwritten in place — a re-run studio shot, a replaced
# composition label — so the old bytes keep being served from the edge long
# after the ficha points at new ones. A replaced label read as "the site
# ignored my photo" for an hour.
PHOTO_CACHE_CONTROL = "public, max-age=300"


def upload_photo(object_name: str, data: bytes) -> str:
    """Upload JPEG bytes; returns the public URL."""
    return upload_object(
        config.PHOTOS_BUCKET,
        object_name,
        data,
        "image/jpeg",
        cache_control=PHOTO_CACHE_CONTROL,
    )


def delete_object(object_name: str) -> None:
    """Best-effort delete of a bucket object; logs but never raises — a
    leftover object is orphaned bytes, not a correctness failure."""
    try:
        requests.delete(
            f"{_STORAGE_API}/storage/v1/b/{config.PHOTOS_BUCKET}/o/"
            f"{requests.utils.quote(object_name, safe='')}",
            headers=_auth_header(),
            timeout=15,
        )
    except requests.RequestException:  # pragma: no cover — dust, not a failure
        logger.warning("Photo delete failed.", extra={"object": object_name})


def promote_photo(tmp_name: str, final_name: str) -> str:
    """Server-side copy tmp → final, best-effort delete of tmp.

    The copy carries the source object's metadata, so the promoted photo
    inherits `PHOTO_CACHE_CONTROL` from the upload that wrote the temporary.
    """
    response = requests.post(
        f"{_STORAGE_API}/storage/v1/b/{config.PHOTOS_BUCKET}/o/"
        f"{requests.utils.quote(tmp_name, safe='')}/copyTo/b/"
        f"{config.PHOTOS_BUCKET}/o/{requests.utils.quote(final_name, safe='')}",
        headers=_auth_header(),
        timeout=30,
    )
    response.raise_for_status()
    delete_object(tmp_name)
    return public_url(final_name)
