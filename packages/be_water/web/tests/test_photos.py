"""Tests for the image pipeline in `photos.py` — process, studio, watermark.

These exercise the real Pillow byte transforms (previously always mocked at the
caller). `studio_photo`'s only external call, Gemini image generation, is
stubbed; everything after it (canvas composition + watermark) runs for real.
"""

import io
from unittest.mock import patch

import pytest
from PIL import Image

from core.sdk.gemini import GeminiError
from packages.be_water.web import photos

_MOD = "packages.be_water.web.photos"


def _img_bytes(size, color="red", fmt="JPEG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, fmt)
    return out.getvalue()


def _has_non_white(img: Image.Image) -> bool:
    return any(px != (255, 255, 255) for px in img.getdata())


# --- process_image ----------------------------------------------------------


def test_process_image_downscales_within_max_side_keeping_aspect():
    out = photos.process_image(_img_bytes((2000, 1000)))
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.mode == "RGB"
    assert max(img.size) <= photos.MAX_SIDE
    assert img.size == (1200, 600)  # aspect ratio preserved


def test_process_image_leaves_small_images_untouched_in_size():
    out = photos.process_image(_img_bytes((300, 400)))
    assert Image.open(io.BytesIO(out)).size == (300, 400)


def test_process_image_strips_exif():
    """Phone photos carry GPS/orientation EXIF and the bucket is public — the
    re-encode must drop it."""
    src = Image.new("RGB", (100, 100), "blue")
    exif = src.getexif()
    exif[274] = 3  # orientation tag
    buf = io.BytesIO()
    src.save(buf, "JPEG", exif=exif)

    out = photos.process_image(buf.getvalue())
    assert 274 not in Image.open(io.BytesIO(out)).getexif()


# --- studio_photo -----------------------------------------------------------


def test_studio_photo_builds_square_watermarked_canvas():
    """Gemini returns an isolated bottle; Pillow squares it onto a 1080 white
    canvas and stamps the watermark bottom-right."""
    bottle = _img_bytes((300, 800), color="black")
    with patch(f"{_MOD}.gemini.generate_image", return_value=bottle):
        out = photos.studio_photo(b"raw-bottle-photo")

    canvas = Image.open(io.BytesIO(out))
    assert canvas.format == "JPEG"
    assert canvas.size == (photos.STUDIO_SIZE, photos.STUDIO_SIZE)  # square
    # Top-left corner stays the white studio background.
    assert canvas.getpixel((5, 5)) == (255, 255, 255)
    # The watermark leaves non-white pixels in the bottom-right quadrant.
    w, h = canvas.size
    assert _has_non_white(canvas.crop((w // 2, h // 2, w, h)))


def test_studio_photo_propagates_gemini_failure():
    """The docstring contract: any failure raises so the caller can fall back
    to the raw photo instead of shipping a broken studio image."""
    with patch(f"{_MOD}.gemini.generate_image", side_effect=GeminiError("overloaded")):
        with pytest.raises(GeminiError):
            photos.studio_photo(b"raw")


# --- _stamp_watermark -------------------------------------------------------


def test_stamp_watermark_marks_bottom_right_only():
    canvas = Image.new("RGB", (photos.STUDIO_SIZE, photos.STUDIO_SIZE), "white")
    photos._stamp_watermark(canvas)
    w, h = canvas.size
    assert _has_non_white(canvas.crop((w // 2, h // 2, w, h)))  # mark present
    assert canvas.getpixel((10, 10)) == (255, 255, 255)  # top-left untouched


# --- public_url -------------------------------------------------------------


def test_upload_photo_asks_for_a_short_cache_on_every_object():
    """Photos are written to stable paths and overwritten in place — a re-run
    studio shot, a replaced composition label. On the bucket default of an
    hour the ficha keeps serving the photo that was just replaced, which reads
    as the site having ignored the upload."""
    with patch(f"{_MOD}.upload_object", return_value="https://x/y.jpg") as mock_upload:
        url = photos.upload_photo("originals/lanjaron.jpg", b"\xff\xd8\xffbytes")

    assert url == "https://x/y.jpg"
    bucket, name, data, content_type = mock_upload.call_args.args
    assert name == "originals/lanjaron.jpg"
    assert data == b"\xff\xd8\xffbytes"
    assert content_type == "image/jpeg"
    assert mock_upload.call_args.kwargs["cache_control"] == "public, max-age=300"


def test_public_url_points_at_the_bucket():
    url = photos.public_url("bezoya.jpg")
    assert url.endswith("/bezoya.jpg")
    assert photos._STORAGE_API in url
