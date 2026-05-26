"""Tests for the Biwenger web application."""

import pytest
from unittest.mock import MagicMock, patch

from packages.biwenger_tools.web import services
from packages.biwenger_tools.web.app import app
from core.domain.models import (
    Clausulazo,
    JusticeEntry,
    LeagueMessage,
    Palmares,
    Participation,
)

# --- Fixtures ---


@pytest.fixture(autouse=True)
def mock_services():
    """Inject mock Google services before each test.

    Drive + Sheets still get a MagicMock so the admin panel + Lloros
    Awards routes don't crash when they touch `services.*` — the content
    routes themselves never touch Google services any more (they read
    Firestore via `repository.*`, which the per-test patches stub out).
    """
    services.drive_service = MagicMock()
    services.sheets_service = MagicMock()
    yield
    services.drive_service = None
    services.sheets_service = None


@pytest.fixture
def client():
    """Create a Flask test client."""
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test_key"
    with app.test_client() as client:
        yield client


def _msg(
    id_hash: str, titulo: str, categoria: str, autor: str = "Jorge"
) -> LeagueMessage:
    return LeagueMessage(
        id_hash=id_hash,
        fecha="01-01-2025 10:00:00",
        autor=autor,
        titulo=titulo,
        contenido=f"<p>cuerpo de {titulo}</p>",
        categoria=categoria,
    )


# --- Session and routing tests ---


def test_home_redirects_to_current_season(client):
    """Verify that / redirects to the current season."""
    with client.session_transaction() as sess:
        sess["current_season"] = "24-25"
    response = client.get("/")
    assert response.status_code == 302
    assert "/24-25/" in response.headers["Location"]


def test_before_request_manages_season(client):
    """Verify that the session is updated with the season from the URL."""
    client.get("/")
    assert client.get_cookie("session") is not None
    client.get("/25-26/")
    with client.session_transaction() as sess:
        assert sess["current_season"] == "25-26"


def test_before_request_ignores_invalid_url(client):
    """Verify that URLs without a valid season do not update the session."""
    client.get("/")
    with client.session_transaction() as sess:
        sess["current_season"] = "24-25"
    client.get("/favicon.ico")
    with client.session_transaction() as sess:
        assert sess["current_season"] == "24-25"


# --- Content route tests ---


@patch("packages.biwenger_tools.web.routes.season.repository.get_messages_by_category")
@patch(
    "packages.biwenger_tools.web.routes.season.repository.count_messages_by_category"
)
def test_comunicados_success(mock_count, mock_get, client):
    """Verify that the comunicados page loads correctly with Firestore data."""
    mock_count.return_value = 2
    mock_get.return_value = [
        _msg("h1", "C1", "comunicado"),
        _msg("h2", "C2", "comunicado"),
    ]
    response = client.get("/24-25/")
    assert response.status_code == 200
    assert b"C1" in response.data
    assert b"C2" in response.data
    # The route asks the repo with the right (season, categoria, limit, offset)
    mock_get.assert_called_once()
    args, kwargs = mock_get.call_args
    assert args[0] == "24-25"
    assert args[1] == "comunicado"
    assert kwargs["limit"] == 7
    assert kwargs["offset"] == 0


@patch(
    "packages.biwenger_tools.web.routes.season.repository.count_messages_by_category",
    side_effect=Exception("Test error"),
)
def test_comunicados_general_exception(mock_count, client):
    """A Firestore failure surfaces as a friendly error message."""
    response = client.get("/24-25/")
    assert response.status_code == 200
    assert b"Ocurri\xc3\xb3 un error al cargar los comunicados" in response.data


@patch("packages.biwenger_tools.web.routes.season.repository.get_messages_by_category")
def test_salseo_success(mock_get, client):
    """Salseo renders datos + crónicas + clausulazos + tabla."""

    def _by_categoria(season, categoria):
        if categoria == "dato":
            return [_msg("h2", "D1", "dato")]
        if categoria == "cronica":
            return [_msg("h5", "CR1", "cronica")]
        return []

    mock_get.side_effect = _by_categoria
    with patch(
        "packages.biwenger_tools.web.routes.season.repository.get_clausulazos",
        return_value=[],
    ), patch(
        "packages.biwenger_tools.web.routes.season.repository.get_tabla_justicia",
        return_value=[],
    ):
        response = client.get("/24-25/salseo")
    assert response.status_code == 200
    assert b"D1" in response.data
    assert b"CR1" in response.data
    # Comunicados must NOT leak into salseo
    assert b"cuerpo de C1" not in response.data


@patch("packages.biwenger_tools.web.routes.season.repository.get_participaciones")
def test_participacion_renders_calculated_counts(mock_get, client):
    """The route turns Participation arrays into their lengths.

    Autor1 has 2 comunicados + 1 dato; Autor2 has 2 datos. The template
    renders those numbers, not the raw arrays — verify the page reflects
    the counts the repo handed back.
    """
    mock_get.return_value = [
        Participation(
            autor="Autor1",
            comunicados=["c1", "c2"],
            datos=["d1"],
            cesiones=[],
            cronicas=[],
        ),
        Participation(
            autor="Autor2",
            comunicados=[],
            datos=["d1", "d2"],
            cesiones=[],
            cronicas=[],
        ),
    ]
    response = client.get("/24-25/participacion")
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    # The raw lists must NOT leak as joined strings
    assert "c1;c2" not in body
    assert "['c1'" not in body

    assert "Autor1" in body
    assert "Autor2" in body
    assert ">2<" in body
    assert ">1<" in body


@patch("packages.biwenger_tools.web.routes.main.repository.get_palmares")
def test_palmares_renders_multas_with_farolillo_marker(mock_get, client):
    """All losers (including the farolillo) live in `multas`; the template
    marks the LAST entry as the farolillo. Podium keys stay direct."""
    mock_get.return_value = [
        Palmares(
            temporada="24-25",
            campeon="Jorge",
            subcampeon="",
            tercero="",
            puntuacion="",
            record_puntos="",
            jornadas_ganadas="",
            multas=[],
        ),
        Palmares(
            temporada="23-24",
            campeon="Dani",
            subcampeon="",
            tercero="",
            puntuacion="",
            record_puntos="",
            jornadas_ganadas="",
            multas=["20", "Pepe"],
        ),
    ]
    response = client.get("/palmares")
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    assert "Jorge" in body  # 24-25 campeon
    assert "Dani" in body  # 23-24 campeon
    assert "20" in body
    assert "Pepe" in body  # last in multas → farolillo


# --- API endpoint tests ---


@patch("packages.biwenger_tools.web.routes.season.get_sheets_data")
def test_api_lloros_ligas_returns_sheets_data(mock_get_sheets, client):
    """The endpoint forwards the sheets_data result for the active season."""
    from packages.biwenger_tools.web import config

    payload = [{"nombre": "Liga A", "headers": ["Pos", "Equipo"], "rows": [["1", "X"]]}]
    mock_get_sheets.return_value = payload
    with patch(
        "packages.biwenger_tools.web.routes.season.config.LIGAS_ESPECIALES_SHEETS",
        {config.TEMPORADA_ACTUAL: "sheet-id-test"},
    ):
        response = client.get("/api/lloros-awards/ligas")
    assert response.status_code == 200
    assert response.get_json() == payload


def test_api_lloros_ligas_returns_empty_when_no_sheet_configured(client):
    """If the active season has no sheet ID mapped, the endpoint returns []
    (not a 500). Important: silent fall-through is a deliberate design choice."""
    with patch(
        "packages.biwenger_tools.web.routes.season.config.LIGAS_ESPECIALES_SHEETS",
        {},
    ):
        response = client.get("/api/lloros-awards/ligas")
    assert response.status_code == 200
    assert response.get_json() == []


@patch("packages.biwenger_tools.web.routes.season.get_sheets_data")
def test_api_lloros_trofeos_returns_sheets_data(mock_get_sheets, client):
    from packages.biwenger_tools.web import config

    payload = [{"nombre": "Pichichi", "headers": ["Goleador"], "rows": [["X"]]}]
    mock_get_sheets.return_value = payload
    with patch(
        "packages.biwenger_tools.web.routes.season.config.TROFEOS_SHEETS",
        {config.TEMPORADA_ACTUAL: "sheet-id-test"},
    ):
        response = client.get("/api/lloros-awards/trofeos")
    assert response.status_code == 200
    assert response.get_json() == payload


# --- Search-data endpoint ---


@patch("packages.biwenger_tools.web.routes.season.repository.get_messages_by_category")
def test_comunicados_search_data_returns_plain_text(mock_get, client):
    """The search-data endpoint strips HTML and only sends search-relevant fields."""
    mock_get.return_value = [
        LeagueMessage(
            id_hash="h1",
            fecha="01-01-2025 10:00:00",
            autor="Jorge",
            titulo="A title",
            contenido="<p>Line one</p><p>Line two</p>",
            categoria="comunicado",
        ),
    ]
    response = client.get("/24-25/comunicados/search-data")
    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload) == 1
    item = payload[0]
    # HTML tags are stripped; line breaks preserved as \n
    assert "<p>" not in item["contenido"]
    assert "Line one" in item["contenido"]
    assert "Line two" in item["contenido"]
    assert "\n" in item["contenido"]
    # All the fields the search box uses
    assert item["titulo"] == "A title"
    assert item["autor"] == "Jorge"
    assert item["fecha"] == "01-01-2025 10:00:00"
    assert item["categoria"] == "comunicado"


# --- Admin panel tests ---


def _seed_csrf(client) -> str:
    """Plant a known CSRF token in the session and return it.

    Form POSTs require the field to match `session["csrf_token"]`; we set both
    sides explicitly so the tests exercise the real path instead of mocking
    `verify_csrf_token`.
    """
    token = "test-csrf-token"
    with client.session_transaction() as sess:
        sess["csrf_token"] = token
    return token


@patch("packages.biwenger_tools.web.app.config.ADMIN_PASSWORD", "test_password")
def test_admin_login_get_page(client):
    """Verify that the admin login page loads correctly."""
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Acceso al VAR" in response.data


@patch("packages.biwenger_tools.web.app.config.ADMIN_PASSWORD", "test_password")
def test_admin_login_post_success(client):
    """Verify that login succeeds with the correct password."""
    token = _seed_csrf(client)
    response = client.post(
        "/admin",
        data={"password": "test_password", "csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess["admin_logged_in"] is True


@patch("packages.biwenger_tools.web.app.config.ADMIN_PASSWORD", "test_password")
def test_admin_login_post_fail(client):
    """Verify that login fails with an incorrect password."""
    token = _seed_csrf(client)
    response = client.post(
        "/admin", data={"password": "wrong_password", "csrf_token": token}
    )
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert "admin_logged_in" not in sess


def test_admin_login_post_rejected_without_csrf(client):
    """POST without a valid csrf_token must not authenticate."""
    with patch(
        "packages.biwenger_tools.web.app.config.ADMIN_PASSWORD", "test_password"
    ):
        response = client.post("/admin", data={"password": "test_password"})
    assert response.status_code in (302, 200)
    with client.session_transaction() as sess:
        assert "admin_logged_in" not in sess


def test_admin_panel_page_loads(client):
    """Verify that the admin panel loads when the user is logged in.

    Panel is now just the scraper-trigger card + system info; the
    Drive-backed file-status table retired with the Firestore migration.
    """
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Scraper Job" in response.data
    assert b"Forzar ejecuci" in response.data


def test_logout_clears_session(client):
    """Verify that the session is cleared on logout."""
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert "admin_logged_in" not in sess


# --- Scraper trigger tests ---


@patch("packages.biwenger_tools.web.routes.admin._trigger_scraper_job")
def test_run_scraper_triggers_job_and_redirects(mock_trigger, client):
    """Logged-in admin POSTing to /admin/run-scraper gets a flash and redirect."""
    mock_trigger.return_value = (True, "Job lanzado correctamente (ejecución: abc123).")
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["csrf_token"] = "test-csrf-token"
    response = client.post(
        "/admin/run-scraper",
        data={"csrf_token": "test-csrf-token"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/admin" in response.headers["Location"]
    mock_trigger.assert_called_once()


@patch("packages.biwenger_tools.web.routes.admin._trigger_scraper_job")
def test_run_scraper_shows_error_flash_on_failure(mock_trigger, client):
    """When the job trigger fails, an error flash is set and admin is shown."""
    mock_trigger.return_value = (False, "Error al lanzar el job: timeout.")
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["csrf_token"] = "test-csrf-token"
    response = client.post(
        "/admin/run-scraper",
        data={"csrf_token": "test-csrf-token"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Error al lanzar el job" in response.data


def test_run_scraper_requires_login(client):
    """Unauthenticated POST to /admin/run-scraper is redirected to admin login."""
    response = client.post("/admin/run-scraper", follow_redirects=False)
    assert response.status_code == 302
    assert "/admin" in response.headers["Location"]


@patch("packages.biwenger_tools.web.routes.admin._trigger_scraper_job")
def test_run_scraper_rejected_without_csrf(mock_trigger, client):
    """Logged-in admin without csrf_token must not trigger the job."""
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    response = client.post("/admin/run-scraper", follow_redirects=False)
    assert response.status_code == 302
    mock_trigger.assert_not_called()


# --- Mercado route tests ---


@patch("packages.biwenger_tools.web.routes.season.repository.get_clausulazos")
@patch("packages.biwenger_tools.web.routes.season.repository.get_tabla_justicia")
def test_mercado_success(mock_tabla, mock_clausulazos, client):
    """Mercado renders clausulazos + tabla de justicia."""
    mock_clausulazos.return_value = [
        Clausulazo(
            fecha="01-01-2025 10:00",
            jugador="Mbappé",
            equipo_vendedor="PSG",
            equipo_comprador="Real Madrid",
            precio=180_000_000,
        ),
    ]
    mock_tabla.return_value = [
        JusticeEntry(
            equipo="Real Madrid",
            total_hechos=3,
            total_recibidos=1,
            punto_de_mira="PSG",
            mayor_agresor="Barça",
            hechos=[],
            recibidos=[],
        ),
    ]
    response = client.get("/24-25/mercado")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "Mbappé" in body
    assert "Real Madrid" in body


@patch(
    "packages.biwenger_tools.web.routes.season.repository.get_clausulazos",
    return_value=[],
)
@patch(
    "packages.biwenger_tools.web.routes.season.repository.get_tabla_justicia",
    return_value=[],
)
def test_mercado_no_data(mock_tabla, mock_clausulazos, client):
    """Mercado page renders without error when both collections are empty."""
    response = client.get("/24-25/mercado")
    assert response.status_code == 200
    assert b"error" not in response.data.lower()
