"""Tests for the photo-audit engine (diagnosis + repair)."""

import io
from unittest.mock import patch

from PIL import Image

from packages.be_water.web import photo_audit
from packages.be_water.web.domain import Water

_MOD = "packages.be_water.web.photo_audit"


def _jpeg(size, color) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG")
    return out.getvalue()


def _water(wid="w", **kw) -> Water:
    return Water(
        id=wid,
        name=kw.pop("name", wid),
        brand="",
        spring="",
        province="",
        community="",
        **kw,
    )


# --- studio detection -------------------------------------------------------


def test_looks_like_studio_true_for_square_white_canvas():
    side = photo_audit._STUDIO_SIDE
    assert photo_audit.looks_like_studio(_jpeg((side, side), "white")) is True


def test_looks_like_studio_false_for_wrong_size():
    side = photo_audit._STUDIO_SIDE
    assert photo_audit.looks_like_studio(_jpeg((800, 600), "white")) is False
    # Right size, dark corners → not the studio canvas.
    assert photo_audit.looks_like_studio(_jpeg((side, side), "black")) is False


# --- scan + suggest ---------------------------------------------------------


def test_scan_catalog_flags_non_studio_main():
    side = photo_audit._STUDIO_SIDE
    catalog = [
        _water("studio-one", photo_url="u1", label_photo_url="l1"),
        _water("raw-one", photo_url="u2"),
        _water("no-photo"),  # skipped: no photo at all
    ]
    images = {"u1": _jpeg((side, side), "white"), "u2": _jpeg((640, 480), "gray")}
    with patch(f"{_MOD}.repository.get_all_waters", return_value=catalog), patch(
        f"{_MOD}.fetch_image", side_effect=lambda url, **_: images[url]
    ):
        statuses = photo_audit.scan_catalog()

    by_id = {s.water_id: s for s in statuses}
    assert set(by_id) == {"studio-one", "raw-one"}  # no-photo excluded
    assert by_id["studio-one"].studio_ok is True
    assert by_id["raw-one"].studio_ok is False
    assert photo_audit.suggest_verdict(by_id["studio-one"]) == photo_audit.OK
    assert photo_audit.suggest_verdict(by_id["raw-one"]) == photo_audit.MAIN_NOT_STUDIO


def test_scan_catalog_survives_unreadable_photo():
    catalog = [_water("broken", photo_url="boom")]
    with patch(f"{_MOD}.repository.get_all_waters", return_value=catalog), patch(
        f"{_MOD}.fetch_image", side_effect=OSError("nope")
    ):
        statuses = photo_audit.scan_catalog()
    assert statuses[0].studio_ok is None  # undetermined, not a crash


# --- repair operations ------------------------------------------------------


def test_rerun_studio_overwrites_main():
    water = _water("bezoya", photo_url="https://x/bezoya.jpg")
    with patch(f"{_MOD}.fetch_image", return_value=b"raw"), patch(
        f"{_MOD}.photos.process_image", return_value=b"proc"
    ), patch(f"{_MOD}.photos.studio_photo", return_value=b"studio") as studio, patch(
        f"{_MOD}.photos.upload_photo", return_value="https://x/bezoya.jpg"
    ) as upload, patch(
        f"{_MOD}.repository.save_water"
    ) as save:
        url = photo_audit.rerun_studio(water)

    studio.assert_called_once_with(b"proc")
    upload.assert_called_once_with("bezoya.jpg", b"studio")
    save.assert_called_once()
    assert water.photo_url == url == "https://x/bezoya.jpg"


def test_replace_label_targets_originals_path():
    water = _water("bezoya")
    with patch(f"{_MOD}.photos.process_image", return_value=b"proc"), patch(
        f"{_MOD}.photos.upload_photo", return_value="https://x/originals/bezoya.jpg"
    ) as upload, patch(f"{_MOD}.repository.save_water"):
        url = photo_audit.replace_label(water, b"raw")
    upload.assert_called_once_with("originals/bezoya.jpg", b"proc")
    assert water.label_photo_url == url


def test_delete_water_removes_every_object_it_owns_then_the_doc():
    """A water with a series owns a pair of objects per analysis on top of the
    current pair. Deleting only the bare paths leaves the history's photos in
    the bucket, paid for and reachable, with no ficha pointing at them."""
    water = _water("bezoya")
    entries = [{"analysis_date": "2025-02"}, {"analysis_date": "2024-01"}]
    with patch(f"{_MOD}.photos.delete_object") as delete_obj, patch(
        f"{_MOD}.repository.list_analyses", return_value=entries
    ), patch(f"{_MOD}.repository.delete_water") as delete_doc:
        photo_audit.delete_water(water)
    assert [c.args[0] for c in delete_obj.call_args_list] == [
        "bezoya__2025-02.jpg",
        "originals/bezoya__2025-02.jpg",
        "bezoya__2024-01.jpg",
        "originals/bezoya__2024-01.jpg",
        "bezoya.jpg",
        "originals/bezoya.jpg",
    ]
    delete_doc.assert_called_once_with("bezoya")
