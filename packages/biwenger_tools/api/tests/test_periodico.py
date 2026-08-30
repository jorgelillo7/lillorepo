"""Tests for publishing a league front page from a Telegram attachment."""

import json
from unittest.mock import patch

import pytest
import requests

from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import periodico

_JPEG = b"\xff\xd8\xff" + b"image-bytes"


@pytest.fixture(autouse=True)
def season(monkeypatch):
    monkeypatch.setattr(config, "CURRENT_SEASON", "26-27")
    monkeypatch.setattr(config, "PERIODICO_BUCKET", "biwenger")
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "tok")


def _publish(caption="Titular", kind="document", image=_JPEG, manifest=None):
    """Run `publish_portada` with the network mocked out.

    Returns `(result, uploads)` where `uploads` is the list of
    `(bucket, name, data, content_type)` written, in order.
    """
    uploads = []

    def _upload(bucket, name, data, content_type, cache_control=None):
        uploads.append((bucket, name, data, content_type, cache_control))
        return f"https://storage.googleapis.com/{bucket}/{name}"

    raw = None if manifest is None else json.dumps(manifest).encode()
    with patch.object(
        periodico, "download_telegram_file", return_value=image
    ), patch.object(periodico, "download_object", return_value=raw), patch.object(
        periodico, "upload_object", side_effect=_upload
    ):
        result = periodico.publish_portada("file-1", caption, kind)
    return result, uploads


# --- Caption parsing ---


def test_caption_without_a_date_publishes_under_today():
    with patch.object(periodico, "_today_madrid", return_value="2026-08-30"):
        fecha, titulo = periodico.parse_caption("Mañana empieza la guerra")

    assert (fecha, titulo) == ("2026-08-30", "Mañana empieza la guerra")


@pytest.mark.parametrize(
    "caption",
    [
        "2026-08-14 Mañana empieza la guerra",
        "2026-08-14 - Mañana empieza la guerra",
        "2026-08-14 | Mañana empieza la guerra".replace("|", "—"),
    ],
)
def test_caption_with_a_date_prefix_wins(caption):
    assert periodico.parse_caption(caption) == (
        "2026-08-14",
        "Mañana empieza la guerra",
    )


def test_caption_keeps_a_headline_that_starts_with_a_number():
    """`2026` alone is not a date prefix — the regex needs the full shape, or
    a headline like "3 fichajes en un día" would lose its first word."""
    with patch.object(periodico, "_today_madrid", return_value="2026-08-30"):
        assert periodico.parse_caption("3 fichajes en un día") == (
            "2026-08-30",
            "3 fichajes en un día",
        )


def test_empty_caption_is_rejected():
    """An empty `titulo` renders a blank card on the web."""
    with pytest.raises(periodico.PortadaRejected):
        periodico.parse_caption("   ")


def test_date_prefix_with_no_headline_is_rejected():
    with pytest.raises(periodico.PortadaRejected):
        periodico.parse_caption("2026-08-14")


def test_impossible_date_is_rejected():
    with pytest.raises(periodico.PortadaRejected) as exc:
        periodico.parse_caption("2026-02-31 Titular")
    assert "2026-02-31" in str(exc.value)


# --- Manifest ---


def test_first_portada_of_a_season_creates_the_manifest():
    result, uploads = _publish(caption="2026-08-14 Titular", manifest=None)

    assert result["published"] is True
    image_upload, manifest_upload = uploads
    assert image_upload[1] == "periodico/26-27/2026-08-14.jpg"
    assert image_upload[3] == "image/jpeg"
    assert manifest_upload[1] == "periodico/26-27/index.json"
    assert json.loads(manifest_upload[2]) == [
        {"fecha": "2026-08-14", "titulo": "Titular"}
    ]


def test_manifest_is_written_with_a_short_cache_so_the_web_sees_it():
    """The image never changes under its date and keeps the bucket default;
    the manifest changes in place and must not sit in the edge cache for an
    hour on top of the web's own TTL."""
    _, (image_upload, manifest_upload) = _publish()

    assert image_upload[4] is None
    assert manifest_upload[4] == "public, max-age=60"


def test_new_portada_is_prepended_newest_first():
    _, uploads = _publish(
        caption="2026-08-14 Nueva",
        manifest=[
            {"fecha": "2026-07-31", "titulo": "Vieja"},
            {"fecha": "2026-08-06", "titulo": "Media"},
        ],
    )

    assert [e["fecha"] for e in json.loads(uploads[1][2])] == [
        "2026-08-14",
        "2026-08-06",
        "2026-07-31",
    ]


def test_same_date_replaces_the_entry_instead_of_appending():
    """One date holds one front page — the image is overwritten, so a second
    entry would render a duplicate card pointing at the same image."""
    result, uploads = _publish(
        caption="2026-08-14 Corregida",
        manifest=[{"fecha": "2026-08-14", "titulo": "Con una errata"}],
    )

    assert json.loads(uploads[1][2]) == [{"fecha": "2026-08-14", "titulo": "Corregida"}]
    assert result["replaced"] is True
    assert "actualizada" in result["message"]


def test_accents_survive_the_manifest():
    _, uploads = _publish(caption="2026-08-14 Mañana empieza la guerra")

    assert "Mañana" in uploads[1][2].decode("utf-8")


def test_unparseable_manifest_is_not_overwritten():
    """Replacing it with a single entry would drop the whole season."""
    with patch.object(
        periodico, "download_telegram_file", return_value=_JPEG
    ), patch.object(
        periodico, "download_object", return_value=b"<html>oops</html>"
    ), patch.object(
        periodico, "upload_object"
    ) as mock_upload:
        with pytest.raises(RuntimeError):
            periodico.publish_portada("f", "Titular", "document")

    mock_upload.assert_not_called()


# --- Rejections ---


def test_non_jpeg_is_rejected_before_anything_is_written():
    """The web builds every URL as `{fecha}.jpg`, so a PNG stored there would
    leave bytes, content type and extension disagreeing."""
    result, uploads = _publish(image=b"\x89PNG\r\n\x1a\n")

    assert result["published"] is False
    assert "JPEG" in result["message"]
    assert uploads == []


def test_file_too_big_is_reported_as_instructions_not_a_failure():
    """getFile refuses over 20 MB. Nothing to retry — the operator resends it
    smaller, so the bot must relay that rather than an error trace."""
    with patch.object(
        periodico,
        "download_telegram_file",
        side_effect=requests.RequestException("file is too big"),
    ), patch.object(periodico, "upload_object") as mock_upload:
        result = periodico.publish_portada("f", "Titular", "document")

    assert result["published"] is False
    assert "20 MB" in result["message"]
    mock_upload.assert_not_called()


def test_missing_headline_is_reported_without_downloading_anything():
    with patch.object(periodico, "download_telegram_file") as mock_download:
        result = periodico.publish_portada("f", "", "document")

    assert result["published"] is False
    assert "titular" in result["message"]
    mock_download.assert_not_called()


def test_write_failure_raises_so_the_bot_reports_an_error():
    """A 403 on the bucket is not the operator's to fix — it must surface as
    an error, not as a cheerful confirmation."""
    with patch.object(
        periodico, "download_telegram_file", return_value=_JPEG
    ), patch.object(periodico, "download_object", return_value=None), patch.object(
        periodico, "upload_object", side_effect=requests.HTTPError("403 Forbidden")
    ):
        with pytest.raises(requests.HTTPError):
            periodico.publish_portada("f", "Titular", "document")


# --- Confirmation ---


def test_a_photo_confirmation_warns_about_recompression():
    """Telegram caps photos at ~1280 px, which loses the body copy of a
    newspaper page — the operator has to know to resend it as a file."""
    result, _ = _publish(kind="photo")

    assert "archivo" in result["message"]


def test_a_document_confirmation_carries_no_warning():
    result, _ = _publish(kind="document")

    assert "recomprime" not in result["message"]
    assert result["url"].endswith(".jpg")
