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


_CSRF = "test-csrf-token"


@pytest.fixture()
def client(monkeypatch):
    from packages.be_water.web import app as app_module

    # Default: empty catalog for the fuzzy-duplicate guard; tests that need
    # one patch repository.get_all_waters themselves (their patch wins).
    monkeypatch.setattr(app_module.repository, "get_all_waters", lambda: [])
    for limiter in (
        app_module._LOGIN_LIMITER,
        app_module._SAVE_LIMITER,
        app_module._PHOTO_LIMITER,
    ):
        limiter.reset()
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        # Seed the session token and inject it into every POST so route
        # tests exercise their real logic; CSRF rejection has its own tests.
        with client.session_transaction() as sess:
            sess["csrf_token"] = _CSRF
        original_post = client.post

        def post_with_csrf(*args, **kwargs):
            data = kwargs.setdefault("data", {})
            if isinstance(data, dict):
                data.setdefault("csrf_token", _CSRF)
            return original_post(*args, **kwargs)

        client.post = post_with_csrf
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
    with patch(f"{_REPO}.touch_user"):
        resp = client.post("/login", data={"nickname": "jorge"})
    assert resp.status_code == 302
    with patch(f"{_REPO}.toggle_favorite", return_value=True) as mock_toggle, patch(
        f"{_REPO}.touch_user"
    ):
        resp = client.post("/favorito/bezoya")
    assert resp.status_code == 302
    mock_toggle.assert_called_once_with("jorge", "bezoya")


def test_login_rejects_bad_nickname(client):
    with patch(f"{_REPO}.touch_user") as mock_touch:
        client.post("/login", data={"nickname": "x y!"})
    mock_touch.assert_not_called()


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
    with patch(f"{_REPO}.touch_user"):
        client.post("/login", data={"nickname": "jorge"})
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.get_favorites", return_value=[catalog[0]]
    ):
        resp = client.get("/recomendar?lugar=Segovia")
    assert resp.status_code == 200
    assert "Bezoya" in resp.get_data(as_text=True)


def test_login_rejected_without_csrf(client):
    with patch(f"{_REPO}.touch_user") as mock_touch:
        client.post("/login", data={"nickname": "jorge", "csrf_token": "wrong"})
    mock_touch.assert_not_called()


def test_add_water_rejected_without_csrf(client):
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save:
        resp = client.post("/anadir", data={"name": "Font Nova", "csrf_token": "wrong"})
    mock_save.assert_not_called()
    assert "sesión ha caducado" in resp.get_data(as_text=True)


def test_photo_uploads_are_rate_limited(client, monkeypatch):
    from packages.be_water.web import app as app_module
    from core.web.ratelimit import RateLimiter

    monkeypatch.setattr(app_module, "_PHOTO_LIMITER", RateLimiter(1, 3600))
    _login(client)
    import io

    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.upload_photo"
    ), patch(f"{_APP}.label_ocr.extract_label", return_value={"name": "X"}):
        first = client.post(
            "/anadir/foto",
            data={"photo": (io.BytesIO(b"raw"), "a.jpg")},
            content_type="multipart/form-data",
        )
        second = client.post(
            "/anadir/foto",
            data={"photo": (io.BytesIO(b"raw"), "b.jpg")},
            content_type="multipart/form-data",
        )
    assert "revisa los valores" in first.get_data(as_text=True)
    assert "Demasiadas fotos" in second.get_data(as_text=True)


def test_form_fields_are_length_capped(client):
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(f"{_REPO}.touch_user"):
        client.post("/anadir", data={"name": "Agua " + "x" * 200})
    saved = mock_save.call_args.args[0]
    assert len(saved.name) == 80


def test_absurd_mineral_values_are_dropped(client):
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(f"{_REPO}.touch_user"):
        client.post(
            "/anadir",
            data={"name": "Font Nova", "tds": "250", "sodium": "-3", "ph": "9999999"},
        )
    saved = mock_save.call_args.args[0]
    assert saved.minerals == {"tds": 250.0}


def test_recommend_falls_back_to_bordering_provinces(client):
    """Madrid has no catalog waters: neighbors' waters are offered instead."""
    catalog = _catalog()  # Cuenca + Segovia — both border Madrid
    with patch(f"{_REPO}.touch_user"):
        client.post("/login", data={"nickname": "jorge"})
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.get_favorites", return_value=[catalog[0]]
    ):
        resp = client.get("/recomendar?lugar=Madrid")
    body = resp.get_data(as_text=True)
    assert "provincias vecinas" in body
    assert "Bezoya" in body  # Segovia water, only non-favorite candidate


def test_places_selector_offers_waterless_provinces(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        resp = client.get("/recomendar")
    assert ">Madrid</option>" in resp.get_data(as_text=True)


_APP = "packages.be_water.web.app"


def _login(client):
    with patch(f"{_REPO}.touch_user"):
        client.post("/login", data={"nickname": "jorge"})


def test_add_water_requires_login(client):
    resp = client.get("/anadir")
    assert resp.status_code == 302


def test_community_shows_aesan_progress(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        resp = client.get("/comunidad")
    body = resp.get_data(as_text=True)
    assert "El registro oficial" in body
    assert "por fichar" in body


def test_about_shows_live_registry_numbers(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        resp = client.get("/acerca")
    body = resp.get_data(as_text=True)
    assert "reconoce oficialmente" in body
    assert "autorellenan" in body


def test_sitemap_covers_info_pages(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        resp = client.get("/sitemap.xml")
    body = resp.get_data(as_text=True)
    assert "/comunidad" in body
    assert "/acerca" in body
    assert "/agua/bezoya" in body


def test_water_photo_becomes_og_image(client):
    catalog = _catalog()
    catalog[1].photo_url = "https://x/bezoya.jpg"
    with patch(f"{_REPO}.get_all_waters", return_value=catalog):
        resp = client.get("/agua/bezoya")
    body = resp.get_data(as_text=True)
    assert '<meta property="og:image" content="https://x/bezoya.jpg">' in body
    assert "summary_large_image" in body


def test_add_form_shows_sections_and_gas_toggle(client):
    _login(client)
    body = client.get("/anadir").get_data(as_text=True)
    assert "Identidad" in body
    assert "Composición de la etiqueta" in body
    assert "Otros valores" in body  # optional section
    assert "Es agua con gas" in body
    for field in ["tds", "sodium", "ph", "silica"]:  # both sections render
        assert f'name="{field}"' in body


def test_add_water_saves_and_redirects(client):
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(f"{_REPO}.touch_user"):
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


def test_add_water_refuses_verified_duplicates(client):
    """A verified water is bottle-checked and data-frozen — never clobbered."""
    _login(client)
    verified = _catalog()[1]
    verified.verified = True
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=verified
    ):
        resp = client.post("/anadir", data={"name": "Bezoya"})
    mock_save.assert_not_called()
    assert resp.status_code == 200
    assert "verificada" in resp.get_data(as_text=True)


def test_add_water_merges_into_unverified_duplicate(client):
    """Saving over an unverified water updates it instead of dead-ending:
    submitted values win, existing photos/minerals/mentions survive."""
    _login(client)
    existing = _catalog()[1]  # bezoya, unverified
    existing.photo_url = "https://x/bezoya.jpg"
    existing.mentions = [{"source": "OCU", "label": "Excelente", "url": "https://x"}]
    existing.verified_fields = ["calcium"]
    existing.added_by = "seed"
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"):
        resp = client.post(
            "/anadir",
            data={"name": "Bezoya", "tds": "26.5", "ocr_fields": "tds"},
        )
    assert resp.status_code == 302
    saved = mock_save.call_args.args[0]
    assert saved.minerals["tds"] == 26.5  # submitted value wins
    assert saved.minerals["calcium"] == 2.4  # existing extra survives
    assert saved.photo_url == "https://x/bezoya.jpg"
    assert saved.mentions == existing.mentions
    assert saved.verified_fields == ["calcium", "tds"]
    assert saved.added_by == "jorge"  # seeded water adopted by the verifier


def test_merge_keeps_original_author_for_user_waters(client):
    """Enriching another user's water must not steal their attribution."""
    _login(client)
    existing = _catalog()[1]
    existing.added_by = "maria"
    existing.added_at = "2026-07-01T00:00:00+00:00"
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"):
        client.post("/anadir", data={"name": "Bezoya", "tds": "26.5"})
    saved = mock_save.call_args.args[0]
    assert saved.added_by == "maria"
    assert saved.added_at == "2026-07-01T00:00:00+00:00"


def _naturis_catalog():
    catalog = _catalog()
    catalog[1].name = "Naturis (Lidl) — Albacete"
    catalog[1].brand = "Lidl"
    catalog[1].retailer = "Lidl"
    return catalog


def test_similar_name_prompts_instead_of_creating(client):
    """«Naturis» vs existing «Naturis (Lidl) — Albacete»: the app asks."""
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(f"{_REPO}.get_all_waters", return_value=_naturis_catalog()):
        resp = client.post("/anadir", data={"name": "Naturis"})
    mock_save.assert_not_called()
    body = resp.get_data(as_text=True)
    assert "Se parece a" in body
    assert "Es la misma — actualizarla" in body
    assert "Es otra — crear nueva" in body


def test_force_new_creates_despite_similarity(client):
    """White labels bottle from several springs — creating anyway is valid."""
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(f"{_REPO}.touch_user"):
        resp = client.post("/anadir", data={"name": "Naturis", "force_new": "1"})
    assert resp.status_code == 302
    assert mock_save.call_args.args[0].id == "naturis"


def test_merge_into_updates_the_confirmed_match(client):
    """Confirming the fuzzy match updates the existing doc, keeping its
    canonical name and retailer."""
    _login(client)
    existing = _naturis_catalog()[1]
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water",
        side_effect=lambda wid: existing if wid == "bezoya" else None,
    ), patch(f"{_REPO}.touch_user"):
        resp = client.post(
            "/anadir",
            data={"name": "Naturis", "merge_into": "bezoya", "tds": "24"},
        )
    assert resp.status_code == 302
    saved = mock_save.call_args.args[0]
    assert saved.id == "bezoya"
    assert saved.name == "Naturis (Lidl) — Albacete"  # canonical name kept
    assert saved.retailer == "Lidl"
    assert saved.minerals["tds"] == 24.0  # form value wins
    assert saved.minerals["calcium"] == 2.4  # existing extra survives


def test_exact_name_different_spring_prompts(client):
    """Font Vella case: same commercial name, another spring — ask, don't
    silently merge two different waters."""
    _login(client)
    existing = _catalog()[1]
    existing.spring = "Font Vella Sacalm"
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ):
        resp = client.post(
            "/anadir",
            data={"name": "Bezoya", "spring": "Font Vella Sigüenza"},
        )
    mock_save.assert_not_called()
    assert "Se parece a" in resp.get_data(as_text=True)


def test_exact_name_different_spring_force_new_disambiguates_id(client):
    _login(client)
    existing = _catalog()[1]
    existing.spring = "Sacalm"
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water",
        side_effect=lambda wid: existing if wid == "bezoya" else None,
    ), patch(f"{_REPO}.touch_user"):
        resp = client.post(
            "/anadir",
            data={"name": "Bezoya", "spring": "Sigüenza", "force_new": "1"},
        )
    assert resp.status_code == 302
    assert mock_save.call_args.args[0].id == "bezoya-siguenza"


def test_verified_water_with_other_spring_still_offers_create(client):
    """A different-spring bottle must not dead-end on the verified error."""
    _login(client)
    existing = _catalog()[1]
    existing.spring = "Sacalm"
    existing.verified = True
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ):
        resp = client.post("/anadir", data={"name": "Bezoya", "spring": "Sigüenza"})
    mock_save.assert_not_called()
    body = resp.get_data(as_text=True)
    assert "Se parece a" in body
    assert "verificada" not in body or "Es otra" in body


def test_retailer_badge_renders_on_cards(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_naturis_catalog()):
        resp = client.get("/")
    assert "🛒 Lidl" in resp.get_data(as_text=True)


def test_slug_strips_accents_so_dedup_catches_lanjaron(client):
    """Regression: «Lanjarón» slugged to 'lanjar-n' and dodged the duplicate
    guard against the existing 'lanjaron' doc."""
    _login(client)
    with patch(f"{_REPO}.save_water"), patch(
        f"{_REPO}.get_water", return_value=None
    ) as mock_get, patch(f"{_REPO}.touch_user"):
        client.post("/anadir", data={"name": "Lanjarón"})
    mock_get.assert_called_once_with("lanjaron")


def test_photo_flow_prefills_form_and_runs_studio(client):
    _login(client)
    with patch(f"{_APP}.config.ADMIN_NICKNAMES", {"jorge"}), patch(
        f"{_APP}.photos.process_image", return_value=b"jpg"
    ), patch(f"{_APP}.photos.studio_photo", return_value=b"studio"), patch(
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
    assert 'name="label_tmp"' in body
    assert "revisa los valores" in body
    assert "estudio" in body
    # Two uploads, both under uploads/ so the lifecycle rule reclaims
    # abandoned forms: {uid}-label.jpg (raw proof) + {uid}.jpg (studio).
    assert mock_upload.call_count == 2
    names = [c.args[0] for c in mock_upload.call_args_list]
    assert names[0].startswith("uploads/")
    assert names[0].endswith("-label.jpg")
    assert names[1].startswith("uploads/")
    assert not names[1].endswith("-label.jpg")
    assert mock_upload.call_args_list[1].args[1] == b"studio"


def test_beauty_photo_becomes_the_display_shot(client):
    """The optional front shot feeds the ficha photo; OCR still reads the
    composition shot."""
    _login(client)
    import io

    with patch(f"{_APP}.photos.process_image", side_effect=[b"label", b"front"]), patch(
        f"{_APP}.photos.upload_photo"
    ) as mock_upload, patch(
        f"{_APP}.label_ocr.extract_label", return_value={"name": "Font Nova"}
    ) as mock_ocr:
        resp = client.post(
            "/anadir/foto",
            data={
                "photo": (io.BytesIO(b"raw-label"), "label.jpg"),
                "beauty": (io.BytesIO(b"raw-front"), "front.jpg"),
            },
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    assert mock_upload.call_count == 2
    label_call, display_call = mock_upload.call_args_list
    assert label_call.args[0].endswith("-label.jpg")
    assert label_call.args[1] == b"label"
    assert display_call.args[1] == b"front"
    mock_ocr.assert_called_once_with(b"label")
    # The processing overlay ships with the form for the next visitor.
    assert 'id="processing"' in resp.get_data(as_text=True)


_AESAN_FAKE = [
    {"name": "Font Nova", "spring": "Font Nova", "place": "X", "province": "Girona"},
    {"name": "Doble", "spring": "Sondeo 1", "place": "A", "province": "Teruel"},
    {"name": "Doble", "spring": "Sondeo 2", "place": "B", "province": "Teruel"},
]


def test_ocr_prefill_completes_provenance_from_aesan(client):
    """The registry fills spring/province/community the label didn't declare."""
    _login(client)
    import io

    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.upload_photo"
    ), patch(
        f"{_APP}.label_ocr.extract_label", return_value={"name": "Font Nova"}
    ), patch(
        f"{_APP}.aesan.AESAN_WATERS", _AESAN_FAKE
    ):
        resp = client.post(
            "/anadir/foto",
            data={"photo": (io.BytesIO(b"raw"), "l.jpg")},
            content_type="multipart/form-data",
        )
    body = resp.get_data(as_text=True)
    assert 'value="Font Nova"' in body  # spring filled from registry
    assert 'value="Girona"' in body
    assert 'value="Cataluña"' in body
    assert "registro AESAN" in body


def test_aesan_prefill_skips_disagreeing_fields_on_multi_spring(client):
    """Two registry springs for the name → only agreeing fields fill."""
    _login(client)
    import io

    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.upload_photo"
    ), patch(f"{_APP}.label_ocr.extract_label", return_value={"name": "Doble"}), patch(
        f"{_APP}.aesan.AESAN_WATERS", _AESAN_FAKE
    ):
        resp = client.post(
            "/anadir/foto",
            data={"photo": (io.BytesIO(b"raw"), "l.jpg")},
            content_type="multipart/form-data",
        )
    body = resp.get_data(as_text=True)
    assert 'value="Teruel"' in body  # both springs agree on the province
    assert "Sondeo" not in body  # spring left empty — the label must decide


def test_non_admin_upload_skips_studio_but_keeps_ocr(client):
    """Everyone gets the free OCR prefill; only admins pay for the studio."""
    _login(client)  # "jorge" is not in the default admin set
    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.studio_photo"
    ) as mock_studio, patch(f"{_APP}.photos.upload_photo") as mock_upload, patch(
        f"{_APP}.label_ocr.extract_label", return_value={"name": "Font Nova"}
    ):
        resp = client.post(
            "/anadir/foto",
            data={"photo": (__import__("io").BytesIO(b"raw"), "label.jpg")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    mock_studio.assert_not_called()
    assert 'value="Font Nova"' in resp.get_data(as_text=True)  # OCR still on
    assert mock_upload.call_args_list[1].args[1] == b"jpg"  # raw photo kept


def test_photo_flow_studio_failure_falls_back_to_raw(client):
    from core.sdk.gemini import GeminiError

    _login(client)
    with patch(f"{_APP}.config.ADMIN_NICKNAMES", {"jorge"}), patch(
        f"{_APP}.photos.process_image", return_value=b"jpg"
    ), patch(f"{_APP}.photos.studio_photo", side_effect=GeminiError("img boom")), patch(
        f"{_APP}.photos.upload_photo"
    ) as mock_upload, patch(
        f"{_APP}.label_ocr.extract_label", return_value={"name": "X"}
    ):
        resp = client.post(
            "/anadir/foto",
            data={"photo": (__import__("io").BytesIO(b"raw"), "label.jpg")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    # Display upload falls back to the processed raw photo.
    assert mock_upload.call_args_list[1].args[1] == b"jpg"
    assert "estudio" not in resp.get_data(as_text=True)


def test_photo_flow_survives_gemini_failure(client):
    """OCR down ≠ photo lost: empty form, photo kept, honest banner."""
    from core.sdk.gemini import GeminiError

    _login(client)
    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.studio_photo", return_value=b"studio"
    ), patch(f"{_APP}.photos.upload_photo"), patch(
        f"{_APP}.label_ocr.extract_label", side_effect=GeminiError("boom")
    ):
        resp = client.post(
            "/anadir/foto",
            data={"photo": (__import__("io").BytesIO(b"raw"), "label.jpg")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'name="photo_tmp"' in body
    assert 'name="label_tmp"' in body
    assert "rellena a mano" in body


def test_add_with_photo_tmp_promotes_both_and_stores_urls(client):
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(
        f"{_APP}.photos.promote_photo",
        side_effect=lambda tmp, final: f"https://x/{final}",
    ) as mock_promote, patch(
        f"{_REPO}.touch_user"
    ):
        resp = client.post(
            "/anadir",
            data={
                "name": "Font Nova",
                "photo_tmp": "uploads/abc.jpg",
                "label_tmp": "originals/abc.jpg",
            },
        )
    assert resp.status_code == 302
    calls = [c.args for c in mock_promote.call_args_list]
    assert ("uploads/abc.jpg", "font-nova.jpg") in calls
    assert ("originals/abc.jpg", "originals/font-nova.jpg") in calls
    water = mock_save.call_args.args[0]
    assert water.photo_url.endswith("font-nova.jpg")
    assert water.label_photo_url.endswith("originals/font-nova.jpg")


def test_full_label_coverage_auto_promotes_to_verified(client):
    """Label proof on file + every declared mineral backed by it → verified."""
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(
        f"{_APP}.photos.promote_photo",
        side_effect=lambda tmp, final: f"https://x/{final}",
    ), patch(
        f"{_REPO}.touch_user"
    ):
        client.post(
            "/anadir",
            data={
                "name": "Font Nova",
                "tds": "180",
                "calcium": "40",
                "ocr_fields": "tds,calcium",
                "photo_tmp": "uploads/abc.jpg",
                "label_tmp": "uploads/abc-label.jpg",
            },
        )
    water = mock_save.call_args.args[0]
    assert water.verified is True
    assert water.verified_fields == ["calcium", "tds"]


def test_hand_typed_extra_mineral_blocks_auto_promotion(client):
    """A value the label didn't declare keeps the ficha in the mixed state."""
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(
        f"{_APP}.photos.promote_photo",
        side_effect=lambda tmp, final: f"https://x/{final}",
    ), patch(
        f"{_REPO}.touch_user"
    ):
        client.post(
            "/anadir",
            data={
                "name": "Font Nova",
                "tds": "180",
                "silica": "12",  # typed by hand, not in ocr_fields
                "ocr_fields": "tds",
                "photo_tmp": "uploads/abc.jpg",
                "label_tmp": "uploads/abc-label.jpg",
            },
        )
    water = mock_save.call_args.args[0]
    assert water.verified is False
    assert water.verified_fields == ["tds"]


def test_profile_shows_traits_and_matches(client):
    catalog = _catalog()
    _login(client)
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.get_favorites", return_value=[catalog[0]]
    ):
        resp = client.get("/perfil")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "mineralización débil" in body  # Solán centroid
    assert "Solán de Cabras" in body  # favorites listed
    assert "Bezoya" in body  # only candidate → suggested match


def test_profile_without_favorites_nudges(client):
    _login(client)
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()), patch(
        f"{_REPO}.get_favorites", return_value=[]
    ):
        resp = client.get("/perfil")
    assert "Marca 2-3 aguas favoritas" in resp.get_data(as_text=True)


def test_sparkling_waters_wear_the_badge(client):
    catalog = _catalog()
    catalog[1].sparkling = True
    with patch(f"{_REPO}.get_all_waters", return_value=catalog):
        home = client.get("/").get_data(as_text=True)
        detail = client.get("/agua/bezoya").get_data(as_text=True)
    assert 'data-gas="1"' in home
    assert home.lower().count("con gas") >= 2  # card badge + filter chip
    assert "con gas" in detail


def test_community_shows_achievements_showcase(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        resp = client.get("/comunidad")
    body = resp.get_data(as_text=True)
    assert "Los logros" in body
    assert "Manantial andante" in body  # even unearned ones are listed


def test_community_page_ranks_contributors(client):
    catalog = _catalog()
    catalog[0].added_by = "jorgelillo"
    catalog[0].verified_fields = ["tds"]
    with patch(f"{_REPO}.get_all_waters", return_value=catalog):
        resp = client.get("/comunidad")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "jorgelillo" in body
    assert "Primera gota" in body


def test_login_touches_last_seen(client):
    with patch(f"{_REPO}.touch_user") as mock_touch:
        client.post("/login", data={"nickname": "jorge"})
    mock_touch.assert_called_once_with("jorge")


def test_about_page_renders(client):
    resp = client.get("/acerca")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "AESAN" in body
    assert "No es consejo médico" in body


def test_add_marks_ocr_fields_as_verified(client):
    """Fields the label declared (and survived review) become verified_fields;
    hand-typed extras don't."""
    _login(client)
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(f"{_REPO}.touch_user"):
        client.post(
            "/anadir",
            data={
                "name": "Font Nova",
                "tds": "180",
                "calcium": "40",
                "sodium": "9",  # typed by hand, not from the label
                "ocr_fields": "tds,calcium,magnesium",  # mg was cleared by user
            },
        )
    water = mock_save.call_args.args[0]
    assert water.verified_fields == ["calcium", "tds"]


def test_seo_plumbing(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        robots = client.get("/robots.txt")
        sitemap = client.get("/sitemap.xml")
        health = client.get("/health")
    assert robots.status_code == 200 and b"Allow" in robots.data
    assert sitemap.status_code == 200
    assert b"/agua/solan-de-cabras" in sitemap.data
    assert health.get_json()["status"] == "ok"
