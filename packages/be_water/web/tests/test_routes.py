"""Route smoke tests with the repository patched (no Firestore)."""

import re
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

    # Defaults so route guards don't hit Firestore: empty catalog for the
    # fuzzy-duplicate check, unknown user for the blocked check. Tests that
    # need real values patch repository themselves (their patch wins).
    monkeypatch.setattr(app_module.repository, "get_all_waters", lambda: [])
    monkeypatch.setattr(app_module.repository, "get_user", lambda nickname: None)
    for limiter in (
        app_module.helpers.LOGIN_LIMITER,
        app_module.helpers.SAVE_LIMITER,
        app_module.helpers.PHOTO_LIMITER,
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


def test_water_detail_renders_provenance_badges(client):
    solan = Water(
        id="solan-de-cabras",
        name="Solán de Cabras",
        brand="Solán de Cabras",
        spring="s",
        province="Cuenca",
        community="Castilla-La Mancha",
        minerals={"tds": 261, "calcium": 59.5, "sodium": 5.2},
        verified_fields=["calcium"],  # ✓ etiqueta
        sources={"tds": "manufacturer", "sodium": "manual", "province": "aesan"},
    )
    with patch(f"{_REPO}.get_all_waters", return_value=[solan]):
        body = client.get("/agua/solan-de-cabras").get_data(as_text=True)
    assert "✓ etiqueta" in body  # calcium (label)
    assert "fabricante" in body  # tds
    assert "a mano" in body  # sodium
    assert "registro AESAN" in body  # province provenance
    assert "sin verificar" not in body  # blanket warning is gone


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


def test_recommend_without_a_place_offers_the_selector_and_a_cta(client):
    """No place chosen yet: the invitation to log in is all there is to show,
    but it is a call to action, not a wall — nothing was searched."""
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


# --- /recomendar is public: the place decides the set, identity the order ----


def _search(client, query, *, favorites=None, catalog=None):
    catalog = _catalog() if catalog is None else catalog
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.get_favorites", return_value=favorites or []
    ):
        return client.get(f"/recomendar?{query}").get_data(as_text=True)


def _listed(body: str) -> list[str]:
    """The water ids the page rendered, in order — every card is a link to
    its ficha."""
    return re.findall(r'href="/agua/([^"]+)"', body)


def test_an_anonymous_visitor_gets_the_waters_not_a_login_wall(client):
    """The catalogue is public on / and /agua/<id>; a region search answered
    with "entra con tu nick" was the page contradicting the rest of the site.
    """
    body = _search(client, "lugar=Cuenca")
    assert "Solán de Cabras" in body
    # The CTA survives, below the results — never instead of them.
    assert body.index("Solán de Cabras") < body.index("Entra con tu nick")


def test_a_registered_visitor_without_favorites_sees_the_same_set(client):
    """Signing in without marking anything must not change what a region
    holds — it was the second of the three dead ends this page had."""
    anonymous = _listed(_search(client, "lugar=Castilla y León"))
    _login(client)  # the session persists on this client from here on
    registered = _listed(_search(client, "lugar=Castilla y León"))
    assert anonymous == registered != []
    assert "Según tus favoritas" not in _search(client, "lugar=Castilla y León")


def test_favorites_personalize_the_order_and_perfil_0_opts_out(client):
    """Same waters both ways — that invariant is what makes the toggle
    honest."""
    catalog = _catalog()
    _login(client)
    personalized = _search(client, "lugar=Castilla y León", favorites=[catalog[0]])
    neutral = _search(client, "lugar=Castilla y León&perfil=0", favorites=[catalog[0]])
    assert "Según tus favoritas" in personalized
    assert "Según tus favoritas" not in neutral
    assert set(_listed(personalized)) == set(_listed(neutral)) != set()


def test_a_place_with_no_waters_and_no_neighbours_invites_the_first(client):
    body = _search(client, "lugar=Illes Balears")
    assert "¿añades tú la primera?" in body
    assert "Cerca de" not in body  # absent, not an empty heading


def test_a_hand_typed_unaccented_place_still_finds_its_waters(client):
    """Unreachable from the dropdown, reachable from a shared link."""
    catalog = _catalog() + [
        Water(
            id="fuensanta",
            name="Fuensanta",
            brand="Fuensanta",
            spring="",
            province="Cádiz",
            community="Andalucía",
            minerals={"tds": 200, "sodium": 4, "calcium": 40},
        )
    ]
    assert "Fuensanta" in _search(client, "lugar=cadiz", catalog=catalog)


def test_a_community_search_offers_its_neighbours(client):
    """`adjacent_provinces` returns [] for a community, so this section was
    empty for half the selector. Segovia (Bezoya) borders Madrid."""
    body = _search(client, "lugar=Comunidad de Madrid")
    assert "Bezoya" in body
    # Madrid has no water of its own, so this is the empty-region wording
    # specifically — an `or` across both branches could not tell them apart.
    assert "provincias vecinas" in body


def test_the_selector_offers_every_community(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        body = client.get("/recomendar").get_data(as_text=True)
    for community in ("Comunidad de Madrid", "Región de Murcia", "Canarias"):
        assert f'value="{community}"' in body


def test_sitemap_lists_place_pages_percent_encoded(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        body = client.get("/sitemap.xml").get_data(as_text=True)
    assert "/recomendar?lugar=Cuenca" in body
    # Accented and spaced names must survive as a valid URL in valid XML.
    assert "/recomendar?lugar=Castilla%20y%20Le%C3%B3n" in body


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

    monkeypatch.setattr(app_module.helpers, "PHOTO_LIMITER", RateLimiter(1, 3600))
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


def test_recommend_offers_bordering_provinces_when_the_place_has_none(client):
    """Madrid has no catalog waters: neighbors' waters are the answer."""
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


def test_nearby_is_offered_even_when_the_place_has_its_own_waters(client):
    """It used to fire only when the region was empty, so the "region +
    nearby" promise was invisible unless you searched Madrid."""
    catalog = _catalog() + [
        Water(
            id="alhama",
            name="Alhama",
            brand="Alhama",
            spring="",
            province="Guadalajara",  # borders Segovia
            community="Castilla-La Mancha",
            minerals={"tds": 300, "sodium": 6, "calcium": 50},
        )
    ]
    body = _search(client, "lugar=Segovia", catalog=catalog)
    assert "Bezoya" in body  # the region itself
    assert "Alhama" in body  # a neighbour, offered alongside — not instead
    assert "Cerca de" in body


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


def _google_login(client, email="admin@x.com"):
    client.set_cookie("g_csrf_token", "gtok")
    with patch(
        f"{_APP}.auth.verify_google_credential",
        return_value={"email": email, "name": "Admin", "picture": ""},
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.get_user", return_value=None):
        return client.post(
            "/auth/google",
            data={"credential": "jwt", "g_csrf_token": "gtok", "csrf_token": ""},
        )


def test_google_routes_hidden_until_configured(client):
    assert client.post("/auth/google", data={}).status_code == 404
    assert client.get("/admin").status_code == 404


def test_google_login_sets_identity_and_derives_nickname(client):
    with patch(f"{_APP}.config.GOOGLE_CLIENT_ID", "cid"):
        resp = _google_login(client, "maria.perez@example.com")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["google_email"] == "maria.perez@example.com"
        assert sess["nickname"] == "maria-perez"


def test_google_login_rejects_csrf_cookie_mismatch(client):
    with patch(f"{_APP}.config.GOOGLE_CLIENT_ID", "cid"):
        client.set_cookie("g_csrf_token", "gtok")
        resp = client.post(
            "/auth/google", data={"credential": "jwt", "g_csrf_token": "OTRO"}
        )
    assert resp.status_code == 403


def test_admin_page_requires_admin_email(client):
    with patch(f"{_APP}.config.GOOGLE_CLIENT_ID", "cid"), patch(
        f"{_APP}.config.ADMIN_EMAILS", {"admin@x.com"}
    ):
        assert client.get("/admin").status_code == 403  # signed out
        _google_login(client, "otra@x.com")
        assert client.get("/admin").status_code == 403  # signed in, not admin
        _google_login(client, "admin@x.com")
        with patch(
            f"{_REPO}.get_all_users",
            return_value={
                "maria": {"favorites": ["a"], "created_at": "2026-07-01T00:00:00"}
            },
        ), patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
            resp = client.get("/admin")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "maria" in body
    assert "Bloquear" in body


def test_admin_block_toggle_and_blocked_login(client):
    with patch(f"{_APP}.config.GOOGLE_CLIENT_ID", "cid"), patch(
        f"{_APP}.config.ADMIN_EMAILS", {"admin@x.com"}
    ):
        _google_login(client, "admin@x.com")
        with patch(
            f"{_REPO}.get_user", return_value={"favorites": [], "blocked": False}
        ), patch(f"{_REPO}.set_user_blocked") as mock_block:
            resp = client.post("/admin/bloquear/maria")
    assert resp.status_code == 302
    mock_block.assert_called_once_with("maria", True)


def test_blocked_nickname_cannot_login_or_add(client):
    with patch(f"{_REPO}.get_user", return_value={"blocked": True}), patch(
        f"{_REPO}.touch_user"
    ) as mock_touch:
        client.post("/login", data={"nickname": "maria"})
    mock_touch.assert_not_called()
    _login(client)  # jorge logs in fine (get_user patched per-call below)
    with patch(f"{_REPO}.get_user", return_value={"blocked": True}), patch(
        f"{_REPO}.save_water"
    ) as mock_save:
        resp = client.post("/anadir", data={"name": "Font Nova"})
    assert resp.status_code == 302
    mock_save.assert_not_called()


def test_community_shows_aesan_progress(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()), patch(
        f"{_REPO}.all_analyses", return_value=[]
    ):
        resp = client.get("/comunidad")
    body = resp.get_data(as_text=True)
    assert "Cobertura del registro AESAN" in body
    assert "por fichar" in body


def test_community_pending_list_shows_unmatched_registry_waters(client):
    """None of `_catalog()`'s waters match the fake registry — all 3 pend."""
    with patch(f"{_APP}.aesan.AESAN_WATERS", _AESAN_FAKE), patch(
        f"{_REPO}.all_analyses", return_value=[]
    ), patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        resp = client.get("/comunidad")
    body = resp.get_data(as_text=True)
    assert "aguas pendientes de fichar" in body
    assert "Font Nova" in body
    assert "Girona" in body
    assert "Teruel" in body


def test_community_shows_complete_registry_message(client):
    catalog = [
        Water(
            id="font-nova",
            name="Font Nova",
            brand="Font Nova",
            spring="",
            province="Girona",
            community="",
        ),
        Water(
            id="doble",
            name="Doble",
            brand="Doble",
            spring="",
            province="Teruel",
            community="",
        ),
    ]
    with patch(f"{_APP}.aesan.AESAN_WATERS", _AESAN_FAKE), patch(
        f"{_REPO}.all_analyses", return_value=[]
    ), patch(f"{_REPO}.get_all_waters", return_value=catalog):
        resp = client.get("/comunidad")
    body = resp.get_data(as_text=True)
    assert "Registro completo" in body
    assert "aguas pendientes de fichar" not in body


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
    # No OCR → both values are hand-entered.
    assert water.sources == {"tds": "manual", "calcium": "manual"}


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
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"):
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
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"):
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
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"):
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
    body = resp.get_data(as_text=True)
    assert "ha pasado por el estudio" not in body  # success note absent
    assert "no pudo retocar la foto" in body  # honest failure note shown


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


def test_photo_flow_gemini_overload_gets_honest_copy(client):
    """A 503/429 from Gemini gets a 'try again later' banner, not a generic one."""
    from core.sdk.gemini import GeminiError

    _login(client)
    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.studio_photo", return_value=b"studio"
    ), patch(f"{_APP}.photos.upload_photo"), patch(
        f"{_APP}.label_ocr.extract_label",
        side_effect=GeminiError("busy", status_code=503),
    ):
        resp = client.post(
            "/anadir/foto",
            data={"photo": (__import__("io").BytesIO(b"raw"), "label.jpg")},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "saturado" in body
    assert "prueba de nuevo en unos minutos" in body


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
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()), patch(
        f"{_REPO}.all_analyses", return_value=[]
    ):
        resp = client.get("/comunidad")
    body = resp.get_data(as_text=True)
    assert "Los logros" in body
    assert "Manantial andante" in body  # even unearned ones are listed


def test_community_page_ranks_contributors(client):
    catalog = _catalog()
    catalog[0].added_by = "jorgelillo"
    catalog[0].verified_fields = ["tds"]
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.all_analyses", return_value=[]
    ):
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


# --- SEO: what a crawler is handed ------------------------------------------


def test_robots_points_at_the_sitemap(client):
    """/robots.txt is the one URL every crawler fetches unprompted, so it is
    where the sitemap has to be announced."""
    body = client.get("/robots.txt").get_data(as_text=True)
    assert "Sitemap: http://localhost/sitemap.xml" in body


def test_absolute_urls_follow_the_forwarded_scheme(client):
    """Cloud Run terminates TLS and forwards the scheme. Without honouring it
    the sitemap advertised 82 http:// URLs that each answered a 302."""
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        body = client.get(
            "/sitemap.xml", headers={"X-Forwarded-Proto": "https"}
        ).get_data(as_text=True)
    assert "https://localhost/agua/solan-de-cabras" in body
    assert "http://localhost" not in body


def test_sitemap_dates_only_what_it_knows(client):
    catalog = _catalog()
    catalog[0].added_at = "2026-03-04T10:00:00+00:00"
    with patch(f"{_REPO}.get_all_waters", return_value=catalog):
        body = client.get("/sitemap.xml").get_data(as_text=True)
    assert "<lastmod>2026-03-04</lastmod>" in body
    # The static pages carry no date rather than today's — a lastmod that
    # changes on every fetch is one a crawler learns to ignore.
    assert body.count("<lastmod>") == 1


def test_canonical_drops_the_parameters_that_only_reorder(client):
    """`?perfil=0` returns the same waters in another order. Left canonical,
    it would compete with the plain URL for the same content."""
    body = _search(client, "lugar=Cuenca&perfil=0")
    assert (
        '<link rel="canonical" href="http://localhost/recomendar?lugar=Cuenca">' in body
    )
    assert "perfil" not in body.split("</head>")[0]


def test_every_public_page_declares_a_canonical_and_an_og_url(client):
    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        for path in ("/", "/agua/bezoya", "/recomendar?lugar=Cuenca", "/acerca"):
            head = client.get(path).get_data(as_text=True).split("</head>")[0]
            assert 'rel="canonical"' in head, path
            assert 'property="og:url"' in head, path
            assert 'property="og:site_name"' in head, path


def test_a_ficha_serves_valid_json_ld(client):
    import json

    with patch(f"{_REPO}.get_all_waters", return_value=_catalog()):
        body = client.get("/agua/bezoya").get_data(as_text=True)
    blob = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', body, re.S
    ).group(1)
    graph = json.loads(blob)["@graph"]  # parses, or the page ships broken markup
    assert graph[0]["@type"] == "Product" and graph[0]["name"] == "Bezoya"
    assert graph[1]["@type"] == "BreadcrumbList"


def test_a_shared_place_link_previews_a_real_bottle(client):
    catalog = _catalog()
    catalog[0].photo_url = "https://cdn.example/solan.jpg"
    body = _search(client, "lugar=Cuenca", catalog=catalog)
    assert '<meta property="og:image" content="https://cdn.example/solan.jpg">' in body
    assert "summary_large_image" in body


# --- analysis date: stale-overwrite guard + revision trail ------------------


def test_an_older_analysis_does_not_touch_the_current_composition(client):
    """The behaviour this feature exists to change.

    An older label used to overwrite the ficha after a warning the contributor
    clicked through — a measurement lost through a dialog. It now joins the
    series and leaves the present alone: `save_water` is never called, and
    nothing is snapshotted because nothing was replaced.
    """
    _login(client)
    existing = _catalog()[1]
    existing.analysis_date = "2025-02"
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(
        f"{_REPO}.save_revision"
    ) as mock_revision, patch(
        f"{_REPO}.get_analysis", return_value=None
    ), patch(
        f"{_REPO}.save_analysis"
    ) as mock_analysis:
        resp = client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "tds": "26.5",
                "ocr_fields": "tds",
                "analysis_date": "2024-01",
            },
        )

    assert resp.status_code == 302
    mock_save.assert_not_called()
    mock_revision.assert_not_called()
    mock_analysis.assert_called_once()
    assert mock_analysis.call_args.args[0].analysis_date == "2024-01"


def test_an_older_analysis_needs_no_confirmation_any_more(client):
    """Nothing is being replaced, so there is nothing to warn about. The
    dialog existed to guard an overwrite that no longer happens."""
    _login(client)
    existing = _catalog()[1]
    existing.analysis_date = "2025-02"
    with patch(f"{_REPO}.save_water"), patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"), patch(
        f"{_REPO}.get_analysis", return_value=None
    ), patch(
        f"{_REPO}.save_analysis"
    ):
        resp = client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "tds": "26.5",
                "ocr_fields": "tds",
                "analysis_date": "2024-01",
            },
        )

    assert resp.status_code == 302, "sin confirmación y sin re-render"


def test_an_undated_label_over_a_dated_one_still_needs_confirming(client):
    """The one case that is still a replacement: an undated composition has no
    slot on the timeline, so saving it does overwrite the ficha and the
    warning still guards it."""
    _login(client)
    existing = _catalog()[1]
    existing.analysis_date = "2025-02"
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"), patch(
        f"{_REPO}.save_analysis"
    ) as mock_analysis:
        resp = client.post(
            "/anadir",
            data={"name": "Bezoya", "tds": "26.5", "ocr_fields": "tds"},
        )

    assert resp.status_code == 200, "el formulario vuelve pidiendo confirmación"
    assert "2025-02" in resp.get_data(as_text=True)
    mock_save.assert_not_called()
    mock_analysis.assert_not_called(), "una composición sin fecha no entra en la serie"


def test_a_newer_label_saves_straight_through_but_still_snapshots(client):
    _login(client)
    existing = _catalog()[1]
    existing.analysis_date = "2024-01"
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.get_analysis"), patch(
        f"{_REPO}.save_analysis"
    ), patch(
        f"{_REPO}.save_revision"
    ) as mock_revision:
        resp = client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "tds": "26.5",
                "ocr_fields": "tds",
                "analysis_date": "2026-03",
            },
        )
    assert resp.status_code == 302
    assert mock_save.call_args.args[0].analysis_date == "2026-03"
    # Reverting a bad edit must not depend on the edit being an older one.
    assert mock_revision.call_args.kwargs["reason"] == "composition_changed"


def test_no_snapshot_when_the_composition_did_not_move(client):
    _login(client)
    existing = _catalog()[1]
    with patch(f"{_REPO}.save_water"), patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision") as mock_revision:
        client.post("/anadir", data={"name": "Bezoya", "spring": "Sierra"})
    mock_revision.assert_not_called()


def test_the_studio_photo_and_the_ocr_run_at_the_same_time(client, monkeypatch):
    """They used to run in a queue and the wait was their sum.

    The studio call alone can take ninety seconds, and the OCR — the one the
    user is actually waiting for, the one that fills the form — started only
    after it finished. Both are independent HTTP calls, so the wall clock
    should be the slower of the two, not the total.
    """
    import io
    import threading

    from packages.be_water.web import config as bw_config

    started = threading.Barrier(2, timeout=5)

    def _slow_studio(_src):
        started.wait()  # only returns if the OCR reached here too
        return b"studio"

    def _slow_ocr(_img):
        started.wait()
        return {"name": "Agua"}

    _login(client)
    monkeypatch.setattr(bw_config, "ADMIN_NICKNAMES", {"tester"})
    with client.session_transaction() as session:
        session["nickname"] = "tester"

    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.upload_photo"
    ), patch(f"{_APP}.photos.studio_photo", side_effect=_slow_studio), patch(
        f"{_APP}.label_ocr.extract_label", side_effect=_slow_ocr
    ):
        response = client.post(
            "/anadir/foto",
            data={"photo": (io.BytesIO(b"raw"), "a.jpg")},
            content_type="multipart/form-data",
        )

    # The barrier would have timed out if either call waited for the other.
    assert response.status_code == 200
    assert "Agua" in response.get_data(as_text=True)


def test_a_failed_ocr_still_saves_the_studio_photo(client, monkeypatch):
    """Running them together must not couple their failures: the studio
    result is uploaded even when the read that follows it fails."""
    import io

    from requests import RequestException

    from packages.be_water.web import config as bw_config

    _login(client)
    monkeypatch.setattr(bw_config, "ADMIN_NICKNAMES", {"tester"})
    with client.session_transaction() as session:
        session["nickname"] = "tester"

    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.upload_photo"
    ) as upload, patch(f"{_APP}.photos.studio_photo", return_value=b"studio"), patch(
        f"{_APP}.label_ocr.extract_label",
        side_effect=RequestException("read timeout"),
    ):
        response = client.post(
            "/anadir/foto",
            data={"photo": (io.BytesIO(b"raw"), "a.jpg")},
            content_type="multipart/form-data",
        )

    assert "rellena a mano" in response.get_data(as_text=True)
    assert any(
        call.args[1] == b"studio" for call in upload.call_args_list
    ), "la foto de estudio se sube aunque el OCR falle"


def test_a_read_timeout_is_reported_as_an_overloaded_reader(client):
    """A timeout is what an overloaded model looks like from here.

    Only a *reply* carries a 429/503, and when Gemini is busy enough the
    request gets no reply at all. That fell through to wording that reads as
    "your photo is unreadable", and the owner re-shot the same bottle three
    times while the model was returning "experiencing high demand".
    """
    import io

    from requests import Timeout

    _login(client)
    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.upload_photo"
    ), patch(f"{_APP}.label_ocr.extract_label", side_effect=Timeout("read timed out")):
        response = client.post(
            "/anadir/foto",
            data={"photo": (io.BytesIO(b"raw"), "a.jpg")},
            content_type="multipart/form-data",
        )

    body = response.get_data(as_text=True)
    assert "saturado" in body
    assert "prueba de nuevo en unos minutos" in body


def test_an_unreadable_label_does_not_blame_the_photo_alone(client):
    """When the reader answers and simply could not parse it, the message
    should not assert which of the two was at fault — we do not know."""
    import io

    from core.sdk.gemini import GeminiError

    _login(client)
    with patch(f"{_APP}.photos.process_image", return_value=b"jpg"), patch(
        f"{_APP}.photos.upload_photo"
    ), patch(
        f"{_APP}.label_ocr.extract_label", side_effect=GeminiError("malformed output")
    ):
        response = client.post(
            "/anadir/foto",
            data={"photo": (io.BytesIO(b"raw"), "a.jpg")},
            content_type="multipart/form-data",
        )

    body = response.get_data(as_text=True)
    assert "puede ser la foto o el lector" in body


# --- Compositions as a dated series ----------------------------------------


def _analysis(date, tds, verified=("tds",), label="originals/x.jpg", photo=None):
    """`photo` defaults to absent, which is the state of every entry the
    backfill wrote — those predate the per-analysis bottle shot."""
    return {
        "water_id": "bezoya",
        "analysis_date": date,
        "minerals": {"tds": tds},
        "verified_fields": list(verified),
        "sources": {},
        "label_photo_url": label,
        "photo_url": photo,
    }


def test_a_resubmission_for_the_same_date_replaces_that_entry(client):
    """Keyed by the analysis date, so a corrected OCR of a past year lands on
    the same document instead of adding a second 2024."""
    _login(client)
    existing = _catalog()[1]
    existing.analysis_date = "2024-01"
    with patch(f"{_REPO}.save_water"), patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"), patch(
        f"{_REPO}.get_analysis", return_value=_analysis("2024-01", 99.0)
    ), patch(
        f"{_REPO}.save_analysis"
    ) as mock_analysis:
        client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "tds": "26.5",
                "ocr_fields": "tds",
                "analysis_date": "2024-01",
            },
        )

    mock_analysis.assert_called_once()
    assert mock_analysis.call_args.args[0].analysis_date == "2024-01"


def test_an_undated_composition_never_enters_the_series(client):
    """Three quarters of the catalog has no analysis date — the label is not
    required to print one — and there is no honest slot for them on a
    timeline."""
    _login(client)
    with patch(f"{_REPO}.save_water"), patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_analysis") as mock_analysis:
        client.post("/anadir", data={"name": "Nueva", "tds": "26.5"})

    mock_analysis.assert_not_called()


def test_each_dated_analysis_keeps_its_own_label_photo(client):
    """`originals/{water_id}.jpg` is one path per water. With a series, the
    second label would overwrite the first one's — destroying the proof of the
    very entry the history exists to keep."""
    _login(client)
    with patch(f"{_REPO}.save_water"), patch(
        f"{_REPO}.get_water", return_value=None
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_analysis"), patch(
        f"{_REPO}.get_analysis", return_value=None
    ), patch(
        f"{_APP}.photos.promote_photo", return_value="https://x/y.jpg"
    ) as promote:
        client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "tds": "26.5",
                "label_tmp": "uploads/abc-label.jpg",
                "analysis_date": "2024-01",
            },
        )

    destinations = [call.args[1] for call in promote.call_args_list]
    assert any(d.endswith("__2024-01.jpg") for d in destinations), destinations


def test_an_older_submission_never_overwrites_the_current_bottle_photo(client):
    """What happened to Peñaclara in production.

    The label got a per-analysis path; the bottle shot did not. An older
    submission promoted its photo to the bare `{water_id}.jpg` **before** the
    outcome branch, so on the history path — where `save_water` never runs —
    the ficha kept its url while the file behind it became the old bottle. The
    replacement is invisible precisely because nothing in Firestore moved.
    """
    _login(client)
    existing = _catalog()[1]
    existing.analysis_date = "2025-02"
    with patch(f"{_REPO}.save_water"), patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"), patch(
        f"{_REPO}.get_analysis", return_value=None
    ), patch(
        f"{_REPO}.save_analysis"
    ), patch(
        f"{_APP}.photos.promote_photo", return_value="https://x/y.jpg"
    ) as promote:
        client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "tds": "26.5",
                "photo_tmp": "uploads/abc.jpg",
                "label_tmp": "uploads/abc-label.jpg",
                "analysis_date": "2024-01",
            },
        )

    destinations = [call.args[1] for call in promote.call_args_list]
    assert destinations, "no photo was promoted at all"
    assert all("__2024-01.jpg" in d for d in destinations), destinations


def test_an_analysis_entry_keeps_the_photos_that_submission_brought(client):
    """`apply_existing` copies the ficha's photos onto a submission that
    brought none, so the entry would store the *current* label as the proof of
    another year's numbers — and the ficha's bottle as that year's bottle,
    which makes the selector look broken: every year, the same picture."""
    _login(client)
    existing = _catalog()[1]
    existing.analysis_date = "2025-02"
    existing.photo_url = "https://x/current.jpg"
    existing.label_photo_url = "https://x/originals/current.jpg"
    with patch(f"{_REPO}.save_water"), patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"), patch(
        f"{_REPO}.get_analysis", return_value=None
    ), patch(
        f"{_REPO}.save_analysis"
    ) as mock_analysis:
        client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "tds": "26.5",
                "analysis_date": "2024-01",
            },
        )

    entry = mock_analysis.call_args.args[0]
    assert entry.photo_url is None
    assert entry.label_photo_url is None


def test_a_dated_entry_carries_only_what_that_label_declared(client):
    """An entry is the record of one measurement. `apply_existing` merges the
    ficha's minerals and unions its verified fields into every submission —
    stored on the entry, that makes a year claim values it never measured and
    a ✓ from a label nobody in that entry photographed. The ficha keeps the
    merge: it is what the catalog and the mineralisation badge read.
    """
    _login(client)
    existing = _catalog()[1]
    existing.analysis_date = "2025-02"
    existing.minerals = {"tds": 26.5, "calcium": 9.0}
    existing.verified_fields = ["tds", "calcium"]
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"), patch(
        f"{_REPO}.get_analysis", return_value=None
    ), patch(
        f"{_REPO}.save_analysis"
    ) as mock_analysis:
        client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "sodium": "1.1",
                "ocr_fields": "sodium",
                "analysis_date": "2024-01",
            },
        )

    entry = mock_analysis.call_args.args[0]
    assert set(entry.minerals) == {"sodium"}
    assert entry.verified_fields == ["sodium"]
    assert set(entry.sources) <= {"sodium"}
    # The ficha is the other half of the rule: it is not narrowed. This save
    # is history, so it does not write one at all.
    mock_save.assert_not_called()


def test_the_ficha_keeps_the_merge_the_entry_does_not(client):
    """The half that protects the search: a newer label declaring fewer
    minerals must not strip the ficha of a residuo seco the catalog reads."""
    _login(client)
    existing = _catalog()[1]
    existing.analysis_date = "2024-01"
    existing.minerals = {"tds": 26.5, "calcium": 9.0}
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"), patch(
        f"{_REPO}.get_analysis", return_value=None
    ), patch(
        f"{_REPO}.save_analysis"
    ) as mock_analysis:
        client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "sodium": "1.1",
                "ocr_fields": "sodium",
                "analysis_date": "2025-06",
            },
        )

    assert mock_save.call_args.args[0].tds == 26.5
    assert set(mock_analysis.call_args.args[0].minerals) == {"sodium"}


def test_only_the_ficha_reads_the_analysis_series(client):
    """The guardrail, asserted where it can actually fail.

    Counting `/agua/bezoya` in the listing proved nothing: `index()` never
    calls `list_analyses`, so the mock was inert and the assertion held for
    any return value — including the day someone made the catalog iterate
    per entry, the exact regression the name claims to guard. Spy on the call
    instead: the series is the ficha's business and nobody else's, because
    every other page must show a water once however many analyses it has.
    """
    catalog = _catalog()
    catalog[1].analysis_date = "2025-02"
    entries = [_analysis("2025-02", 26.5), _analysis("2024-01", 30.0)]

    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses", return_value=entries
    ) as spy:
        client.get("/")
        client.get("/recomendar?lugar=Segovia")
        assert spy.call_count == 0, "el catálogo no debe leer la serie"

        listing = client.get("/")
        assert listing.get_data(as_text=True).count("/agua/bezoya") == 1

        client.get("/agua/bezoya")
        assert spy.call_count == 1, "la ficha sí"


def test_both_photos_can_be_opened_full_size(client):
    """A label shot is small print rendered 64 units tall on a phone — proof
    nobody can actually check. Both the bottle and the label open in the
    viewer, and the label keeps its `href` so it still opens without JS."""
    catalog = _catalog()
    catalog[1].photo_url = "https://x/bezoya.jpg"
    catalog[1].label_photo_url = "https://x/originals/bezoya.jpg"
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses", return_value=[]
    ):
        body = client.get("/agua/bezoya").get_data(as_text=True)

    assert 'data-caption="Botella de Bezoya"' in body
    assert 'data-caption="Etiqueta de Bezoya' in body
    assert 'href="https://x/originals/bezoya.jpg"' in body


def test_a_mineral_bar_is_scaled_by_that_mineral_not_a_shared_ceiling(client):
    """One constant for every mineral pinned half the catalog at full width:
    sodium at 500 and sodium at 5000 drew the same bar."""
    catalog = _catalog()
    catalog[0].minerals = {"sodium": 1000.0}
    catalog[1].minerals = {"sodium": 100.0}
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses", return_value=[]
    ):
        body = client.get("/agua/bezoya").get_data(as_text=True)

    # 100 of a catalog whose most sodic water holds 1000 — a tenth, not a
    # quarter of an arbitrary 400.
    assert "width: 10.0%" in body


def test_every_provenance_badge_links_to_an_explanation_that_exists(client):
    """The badges said what they meant only through `title=`, which does
    nothing on a touch screen — and the page they pointed at explained three
    of the four words it used, never "a mano". A reader on a phone had no way
    to find out where a number came from.

    Ties the two pages together: every anchor the ficha links to has to exist
    in `/acerca`, so renaming a section breaks the build instead of leaving a
    link that scrolls nowhere.
    """
    catalog = _catalog()
    catalog[1].minerals = {"tds": 26.5, "sodium": 1.1, "calcium": 9.0}
    catalog[1].verified_fields = ["tds"]
    catalog[1].sources = {"sodium": "manual", "calcium": "manufacturer"}
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses", return_value=[]
    ):
        ficha = client.get("/agua/bezoya").get_data(as_text=True)
        about = client.get("/acerca").get_data(as_text=True)

    anchors = set(re.findall(r'href="[^"]*#(fuente[a-z-]*)"', ficha))
    assert anchors == {
        "fuente-etiqueta",
        "fuente-a-mano",
        "fuente-fabricante",
        "fuentes",  # the legend at the foot of the card
    }
    for name in anchors:
        assert f'id="{name}"' in about, f"/acerca no explica {name}"


def test_the_home_count_does_not_treat_a_blank_province_as_one(client):
    """Live, the home page said 23 provinces over 22. Province is optional
    end to end — the add form does not require it — and Jinja's `unique`
    counted the empty string as a province of its own."""
    catalog = _catalog()
    catalog[0].province = "Segovia"
    catalog[1].province = ""
    with patch(f"{_REPO}.get_all_waters", return_value=catalog):
        body = client.get("/").get_data(as_text=True)

    assert ">1</span> provincias" in body, "una provincia real, no dos"


def test_a_past_analysis_does_not_advertise_the_present_numbers(client):
    """The page's own metadata must describe the page. With `?analisis=` the
    body shows one composition while the head described another: a crawler
    or a shared link quoted this year's residuo seco under last year's URL.
    The canonical tag is what consolidates the variants — it drops `analisis`
    — so the head is free to tell the truth about what is on screen."""
    catalog = _catalog()
    catalog[1].analysis_date = "2025-02"
    catalog[1].minerals = {"tds": 26.5}
    catalog[1].photo_url = "https://x/bezoya.jpg"
    past = _analysis("2024-01", 30.0, photo="https://x/bezoya__2024-01.jpg")
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses", return_value=[_analysis("2025-02", 26.5), past]
    ):
        body = client.get("/agua/bezoya?analisis=2024-01").get_data(as_text=True)

    head = body.split("</head>")[0]
    assert "30" in head and "26.5" not in head, "la meta cita el análisis mostrado"
    assert "bezoya__2024-01.jpg" in head, "y su botella"
    # The canonical drops the parameter, which is what keeps the variants from
    # competing with the ficha for the same search.
    assert '<link rel="canonical" href="http://localhost/agua/bezoya">' in head


def test_a_mineral_reads_the_same_however_it_reached_the_catalog(client):
    """The seed stores plain ints and the form floats everything, so the same
    number printed as `261` on one ficha and `667.0` on the next depending
    only on how the water got in."""
    catalog = _catalog()
    catalog[1].minerals = {"tds": 667.0, "calcium": 2.19}
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses", return_value=[]
    ):
        body = client.get("/agua/bezoya").get_data(as_text=True)

    # Only what a reader sees: the JSON-LD carries `667.0` on purpose, because
    # there it is a number and not a piece of text.
    visible = re.sub(r"(?s)<script.*?</script>", "", body)
    assert ">667<" in visible and "667.0" not in visible
    assert "2.19" in visible, "un decimal de verdad se queda"


def test_a_past_analysis_swaps_the_numbers_and_its_verification(client):
    """The tick must travel with its year. Showing 2024's values under 2025's
    "confirmado por etiqueta" would claim a label nobody in that entry ever
    photographed."""
    catalog = _catalog()
    catalog[1].analysis_date = "2025-02"
    catalog[1].minerals = {"tds": 26.5}
    catalog[1].verified_fields = ["tds"]
    past = _analysis("2024-01", 30.0, verified=[])
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses", return_value=[_analysis("2025-02", 26.5), past]
    ):
        response = client.get("/agua/bezoya?analisis=2024-01")

    body = response.get_data(as_text=True)
    assert "30" in body, "los valores son los de 2024"
    assert "análisis anterior" in body
    # The point: 2025's label confirmed tds, 2024's did not. Rendering the
    # past values under the present ✓ would assert a photograph that entry
    # never had. Asserting only on the numbers passes with the ticks left
    # behind — this is what makes the test worth having.
    # The per-field marker, not the legend at the foot of the page, which
    # explains the sources and is always there.
    marker = 'title="Confirmado de foto de etiqueta"'
    assert marker not in body

    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses", return_value=[_analysis("2025-02", 26.5), past]
    ):
        current = client.get("/agua/bezoya").get_data(as_text=True)
    assert marker in current, "el actual sí está confirmado por etiqueta"


def test_a_past_analysis_shows_the_bottle_of_its_own_year(client):
    """A label redesign is part of what changed between analyses, so the
    bottle follows the year. Without this the selector moves the numbers and
    leaves the same picture on screen, which reads as a page that did not
    react."""
    catalog = _catalog()
    catalog[1].analysis_date = "2025-02"
    catalog[1].photo_url = "https://x/bezoya.jpg"
    past = _analysis("2024-01", 30.0, photo="https://x/bezoya__2024-01.jpg")
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses", return_value=[_analysis("2025-02", 26.5), past]
    ):
        body = client.get("/agua/bezoya?analisis=2024-01").get_data(as_text=True)

    assert "bezoya__2024-01.jpg" in body
    assert 'src="https://x/bezoya.jpg"' not in body


def test_an_analysis_with_no_bottle_of_its_own_keeps_the_ficha_s(client):
    """The bottle is illustration, not evidence: an entry that never had one —
    every backfilled entry — is better shown with today's than with none. The
    label does not fall back; that one is evidence."""
    catalog = _catalog()
    catalog[1].analysis_date = "2025-02"
    catalog[1].photo_url = "https://x/bezoya.jpg"
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses",
        return_value=[_analysis("2025-02", 26.5), _analysis("2024-01", 30.0)],
    ):
        body = client.get("/agua/bezoya?analisis=2024-01").get_data(as_text=True)

    assert 'src="https://x/bezoya.jpg"' in body


def test_an_unknown_analysis_is_a_404_not_the_current_one(client):
    """Silently falling back to the present would show one year's numbers
    under another year's URL."""
    catalog = _catalog()
    catalog[1].analysis_date = "2025-02"
    with patch(f"{_REPO}.get_all_waters", return_value=catalog), patch(
        f"{_REPO}.list_analyses", return_value=[_analysis("2025-02", 26.5)]
    ):
        assert client.get("/agua/bezoya?analisis=1999").status_code == 404


def test_a_verified_water_still_accepts_an_older_analysis(client):
    """Reported: photographing an older label of `penaclara` was refused with
    "ya está verificada — no se puede sobrescribir".

    It was not going to overwrite anything. The guard ran before the
    submission's date was parsed and refused everything, blocking the one case
    the history exists for — an older label of a water already bottle-checked.
    """
    _login(client)
    existing = _catalog()[1]
    existing.verified = True
    existing.analysis_date = "2025-02"
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_revision"), patch(
        f"{_REPO}.get_analysis", return_value=None
    ), patch(
        f"{_REPO}.save_analysis"
    ) as mock_analysis:
        response = client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "tds": "26.5",
                "ocr_fields": "tds",
                "analysis_date": "2024-01",
            },
        )

    assert response.status_code == 302, "el histórico acepta el análisis viejo"
    mock_analysis.assert_called_once()
    mock_save.assert_not_called(), "y la ficha verificada no se toca"


def test_a_verified_water_still_refuses_to_be_overwritten(client):
    """The guard's real job survives: a newer or undated submission for a
    bottle-checked water is still refused."""
    _login(client)
    existing = _catalog()[1]
    existing.verified = True
    existing.analysis_date = "2025-02"
    with patch(f"{_REPO}.save_water") as mock_save, patch(
        f"{_REPO}.get_water", return_value=existing
    ), patch(f"{_REPO}.touch_user"), patch(f"{_REPO}.save_analysis") as mock_analysis:
        response = client.post(
            "/anadir",
            data={
                "name": "Bezoya",
                "tds": "26.5",
                "ocr_fields": "tds",
                "analysis_date": "2026-05",
            },
        )

    assert response.status_code == 200
    assert "verificada" in response.get_data(as_text=True)
    mock_save.assert_not_called()
    mock_analysis.assert_not_called()
