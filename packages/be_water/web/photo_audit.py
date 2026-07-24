"""Photo-audit engine for be_water: diagnose and repair already-uploaded shots.

A ficha carries two photos:
  * ``photo_url``        — the display shot; for admins it goes through the
    studio treatment (1080² white background + watermark).
  * ``label_photo_url``  — the composition label ("ver etiqueta de composición"),
    kept as verification proof under ``originals/``.

Two things can be wrong, hence two verdicts (``both`` = the pair):
  * ``main_not_studio`` — the display shot never got the studio treatment.
    Machine-detectable: the studio pipeline is the only thing that emits an
    exactly ``STUDIO_SIZE²`` canvas with white corners.
  * ``wrong_label``     — the label shot is the wrong photo. Subjective; a
    human has to look.

The CLI (``scripts/audit_photos.py``) drives the diagnosis; the future admin
page reuses the same ``scan_catalog`` + repair functions. Nothing here mutates
production unless a caller invokes a repair function explicitly.
"""

import io
from dataclasses import dataclass
from typing import Optional

import requests
from PIL import Image

from core.utils import get_logger
from packages.be_water.web import photos, repository
from packages.be_water.web.domain import Water

logger = get_logger(__name__)

# Verdicts — plain strings so they serialise straight into the JSON map (and,
# later, a Firestore field).
OK = "ok"
MAIN_NOT_STUDIO = "main_not_studio"
WRONG_LABEL = "wrong_label"
BOTH = "both"
NO_PHOTO = "no_photo"

FIXABLE = (MAIN_NOT_STUDIO, WRONG_LABEL, BOTH)

_STUDIO_SIDE = photos.STUDIO_SIZE
# The studio canvas is pure white (255); JPEG rounding can shave a couple of
# levels off the corners, so accept anything near-white.
_WHITE_MIN = 250


@dataclass
class PhotoStatus:
    water_id: str
    name: str
    has_main: bool
    has_label: bool
    # None when undetermined (no main shot, or the fetch/decoding failed).
    studio_ok: Optional[bool]
    main_url: Optional[str]
    label_url: Optional[str]


def fetch_image(url: str, timeout: int = 20) -> bytes:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def looks_like_studio(image_bytes: bytes) -> bool:
    """True when the image matches the studio output: a square STUDIO_SIZE
    canvas with white corners. Heuristic, but reliable — no other pipeline
    produces this exact shape."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if img.width != _STUDIO_SIDE or img.height != _STUDIO_SIDE:
        return False
    w, h = img.width, img.height
    corners = [(1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)]
    return all(min(img.getpixel(c)) >= _WHITE_MIN for c in corners)


def suggest_verdict(status: PhotoStatus) -> str:
    """Machine part of the diagnosis. Studio detection is trustworthy; label
    correctness is not, so a readable studio photo suggests OK and the human
    still confirms the label by eye."""
    if not status.has_main and not status.has_label:
        return NO_PHOTO
    if status.studio_ok is False:
        return MAIN_NOT_STUDIO
    return OK


def scan_catalog(catalog: Optional[list[Water]] = None) -> list[PhotoStatus]:
    """Every water carrying at least one photo, with studio detection run on
    the main shot. Read-only; safe to run against production."""
    catalog = catalog if catalog is not None else repository.get_all_waters()
    statuses = []
    for water in catalog:
        if not water.photo_url and not water.label_photo_url:
            continue
        studio_ok = None
        if water.photo_url:
            try:
                studio_ok = looks_like_studio(fetch_image(water.photo_url))
            except (requests.RequestException, OSError) as exc:
                logger.warning(
                    "Main photo unreadable during audit.",
                    extra={"water_id": water.id, "error": str(exc)[:200]},
                )
        statuses.append(
            PhotoStatus(
                water_id=water.id,
                name=water.name,
                has_main=bool(water.photo_url),
                has_label=bool(water.label_photo_url),
                studio_ok=studio_ok,
                main_url=water.photo_url,
                label_url=water.label_photo_url,
            )
        )
    return statuses


# --- Repair operations ------------------------------------------------------
# Used by the CLI's --fix pass and, later, the admin page. Each mutates
# production (GCS + Firestore) and returns the resulting state.


def set_main_photo(water: Water, image_bytes: bytes, studioise: bool = True) -> str:
    """Replace the display photo from raw bytes. With ``studioise`` (default)
    the bytes go through the studio treatment first. Returns the public URL."""
    processed = photos.process_image(image_bytes)
    final = photos.studio_photo(processed) if studioise else processed
    url = photos.upload_photo(f"{water.id}.jpg", final)
    water.photo_url = url
    repository.save_water(water)
    return url


def rerun_studio(water: Water) -> str:
    """Re-generate the studio photo from the current display shot and overwrite
    it — the fix for a ``main_not_studio`` water that already has a good raw
    front shot. Requires GEMINI_API_KEY."""
    if not water.photo_url:
        raise ValueError(f"{water.id} has no main photo to studio-ise")
    return set_main_photo(water, fetch_image(water.photo_url), studioise=True)


def replace_label(water: Water, image_bytes: bytes) -> str:
    """Replace the composition-label shot (the ``originals/`` object). Returns
    the public URL."""
    processed = photos.process_image(image_bytes)
    url = photos.upload_photo(f"originals/{water.id}.jpg", processed)
    water.label_photo_url = url
    repository.save_water(water)
    return url


def delete_water(water: Water) -> None:
    """Remove the ficha entirely: both bucket objects then the Firestore doc.
    Photo deletes are best-effort; the doc delete is the authoritative part."""
    photos.delete_object(f"{water.id}.jpg")
    photos.delete_object(f"originals/{water.id}.jpg")
    repository.delete_water(water.id)
