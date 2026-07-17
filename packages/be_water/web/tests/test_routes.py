"""Route smoke tests with the repository patched (no Firestore)."""

from unittest.mock import patch

import pytest

from packages.be_water.web.domain import Water

_REPO = "packages.be_water.web.app.repository"


def _catalog():
    return [
        Water(
            id="solan-de-cabras",
            name="Solán de Cabras",
            brand="Solán de Cabras",
            spring="Solán de Cabras",
            province="Cuenca",
            community="Castilla-La Mancha",
            minerals={"tds": 261, "sodium": 5.2, "calcium": 59.5},
        ),
        Water(
            id="bezoya",
            name="Bezoya",
            brand="Bezoya",
            spring="Bezoya",
            province="Segovia",
            community="Castilla y León",
            minerals={"tds": 27, "sodium": 1.2, "calcium": 2.4},
        ),
    ]


@pytest.fixture()
def client():
    from packages.be_water.web.app import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_renders_catalog(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Solán de Cabras" in body
    assert "Bezoya" in body
    assert "muy débil" in body


def test_water_detail_shows_similars(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        resp = client.get("/agua/solan-de-cabras")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Residuo seco" in body
    assert "Bezoya" in body  # only other water → appears as similar


def test_water_detail_404(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        resp = client.get("/agua/no-existe")
    assert resp.status_code == 404


def test_login_sets_session_and_favorite_toggles(client):
    with patch(f"{_REPO}.ensure_user", return_value={"favorites": []}):
        resp = client.post("/login", data={"nickname": "jorge"})
    assert resp.status_code == 302
    with patch(f"{_REPO}.toggle_favorite", return_value=True) as mock_toggle:
        resp = client.post("/favorito/bezoya")
    assert resp.status_code == 302
    mock_toggle.assert_called_once_with("jorge", "bezoya")


def test_login_rejects_bad_nickname(client):
    with patch(f"{_REPO}.ensure_user") as mock_ensure:
        client.post("/login", data={"nickname": "x y!"})
    mock_ensure.assert_not_called()


def test_favorite_without_login_is_noop(client):
    with patch(f"{_REPO}.toggle_favorite") as mock_toggle:
        resp = client.post("/favorito/bezoya")
    assert resp.status_code == 302
    mock_toggle.assert_not_called()


def test_recommend_needs_place_and_favorites(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        resp = client.get("/recomendar")
    assert resp.status_code == 200
    assert "Entra con tu nick" in resp.get_data(as_text=True)


def test_recommend_with_favorites(client):
    catalog = _catalog()
    with patch(f"{_REPO}.ensure_user", return_value={"favorites": []}):
        client.post("/login", data={"nickname": "jorge"})
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.get_favorites", return_value=[catalog[0]]
    ):
        resp = client.get("/recomendar?lugar=Segovia")
    assert resp.status_code == 200
    assert "Bezoya" in resp.get_data(as_text=True)


_APP = "packages.be_water.web.app"


def _login(client):
    with patch(f"{_REPO}.ensure_user", return_value={"favorites": []}):
        client.post("/login", data={"nickname": "jorge"})


def test_add_water_requires_login(client):
    resp = client.get("/anadir")
    assert resp.status_code == 302


def test_add_water_saves_and_redirects(client):
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ):
        resp = client.post(
            "/anadir",
            data={
                "name": "Agua de Benassal",
                "province": "Castellón",
                "tds": "310",
                "calcium": "80,5",
            },
        )
    assert resp.status_code == 302
    water = mock_save.call_args.args[0]
    assert water.id == "agua-de-benassal"
    assert water.minerals["tds"] == 310.0
    assert water.minerals["calcium"] == 80.5  # comma decimal accepted
    assert water.added_by == "jorge"


def test_add_water_refuses_duplicates(client):
    """An existing (possibly verified) water must never be clobbered."""
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=_catalog()[1]
    ):
        resp = client.post("/anadir", data={"name": "Bezoya"})
    mock_save.assert_not_called()
    assert resp.status_code == 200
    assert "ya existe" in resp.get_data(as_text=True)


def test_photo_flow_prefills_form_from_gemini(client):
    _login(client)
    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.upload_photo"
    ) as mock_upload, patch(
        f"{_APP}.label_ocr.extract_label",
        return_value={"name": "Font Nova", "tds": 180, "spring": None},
    ):
        resp = client.post(
            "/anadir/foto",
            data={"photo": (__import__("io").BytesIO(b"raw"), "label.jpg")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'value="Font Nova"' in body
    assert 'value="180"' in body
    assert 'name="photo_tmp"' in body
    assert "revisa los valores" in body
    mock_upload.assert_called_once()


def test_photo_flow_survives_gemini_failure(client):
    """OCR down ≠ photo lost: empty form, photo kept, honest banner."""
    from core.sdk.gemini import GeminiError

    _login(client)
    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.upload_photo"
    ), patch(f"{_APP}.label_ocr.extract_label", side_effect=GeminiError("boom")):
        resp = client.post(
            "/anadir/foto",
            data={"photo": (__import__("io").BytesIO(b"raw"), "label.jpg")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'name="photo_tmp"' in body
    assert "rellena a mano" in body


def test_add_with_photo_tmp_promotes_and_stores_url(client):
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(
        f"{_APP}.photos.promote_photo",
        return_value="https://storage.googleapis.com/be-water-photos/font-nova.jpg",
    ) as mock_promote:
        resp = client.post(
            "/anadir",
            data={"name": "Font Nova", "photo_tmp": "uploads/abc.jpg"},
        )
    assert resp.status_code == 302
    mock_promote.assert_called_once_with("uploads/abc.jpg", "font-nova.jpg")
    water = mock_save.call_args.args[0]
    assert water.photo_url.endswith("font-nova.jpg")


def test_seo_plumbing(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        robots = client.get("/robots.txt")
        sitemap = client.get("/sitemap.xml")
        health = client.get("/health")
    assert robots.status_code == 200 and b"Allow" in robots.data
    assert sitemap.status_code == 200
    assert b"/agua/solan-de-cabras" in sitemap.data
    assert health.get_json()["status"] == "ok"
