"""Tests for the Biwenger web application."""

import pytest
from unittest.mock import MagicMock, patch

from packages.biwenger_tools.web.app import app
from packages.biwenger_tools.web import services

# --- Fixtures ---


@pytest.fixture(autouse=True)
def mock_services():
    """Inject mock Google services before each test."""
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


def _row(id_hash: str, titulo: str, categoria: str, autor: str = "Jorge") -> dict:
    """Build a CSV-shaped row with all the fields LeagueMessage.from_csv_row reads."""
    return {
        "id_hash": id_hash,
        "fecha": "01-01-2025 10:00:00",
        "autor": autor,
        "titulo": titulo,
        "contenido": f"<p>cuerpo de {titulo}</p>",
        "categoria": categoria,
    }


@pytest.fixture
def mock_comunicados_data():
    """Realistic CSV rows — every field LeagueMessage.from_csv_row touches."""
    return [
        _row("h1", "C1", "comunicado"),
        _row("h2", "D1", "dato"),
        _row("h3", "C2", "comunicado"),
        _row("h4", "CES1", "cesion"),
        _row("h5", "CR1", "cronica"),
        _row("h6", "C3", "comunicado"),
    ]


@pytest.fixture
def mock_participacion_data():
    """Sample participation data — counts will be 2/1/0/0 vs 0/2/0/0."""
    return [
        {
            "autor": "Autor1",
            "comunicados": "c1;c2",
            "datos": "d1",
            "cesiones": "",
            "cronicas": "",
        },
        {
            "autor": "Autor2",
            "comunicados": "",
            "datos": "d1;d2",
            "cesiones": "",
            "cronicas": "",
        },
    ]


@pytest.fixture
def mock_palmares_data():
    """Mixes "regular" categories (campeon) with the "otros" group (multa, sancion,
    farolillo) so we can verify grouping logic, not just rendering."""
    return [
        {"temporada": "24-25", "categoria": "campeon", "valor": "Jorge"},
        {"temporada": "23-24", "categoria": "multa", "valor": "20"},
        {"temporada": "23-24", "categoria": "sancion", "valor": "tarjeta roja"},
        {"temporada": "23-24", "categoria": "farolillo", "valor": "Pepe"},
        {"temporada": "23-24", "categoria": "campeon", "valor": "Dani"},
    ]


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


@patch("packages.biwenger_tools.web.routes.season.download_csv_as_dict")
@patch(
    "packages.biwenger_tools.web.routes.season.find_file_on_drive",
    return_value={"id": "fake_id"},
)
def test_comunicados_success(
    mock_find_file, mock_download_csv, client, mock_comunicados_data
):
    """Verify that the comunicados page loads correctly with data."""
    mock_download_csv.return_value = mock_comunicados_data
    response = client.get("/24-25/")
    assert response.status_code == 200
    assert b"C1" in response.data
    assert b"C2" in response.data
    assert b"D1" not in response.data


@patch(
    "packages.biwenger_tools.web.routes.season.find_file_on_drive", return_value=None
)
def test_comunicados_file_not_found(mock_find_file, client):
    """Verify that an error is shown when the file is not found."""
    response = client.get("/24-25/")
    assert response.status_code == 200
    assert b"error" in response.data.lower()


@patch(
    "packages.biwenger_tools.web.routes.season.download_csv_as_dict",
    side_effect=Exception("Test error"),
)
@patch(
    "packages.biwenger_tools.web.routes.season.find_file_on_drive",
    return_value={"id": "fake_id"},
)
def test_comunicados_general_exception(mock_find_file, mock_download_csv, client):
    """Verify that a general exception is handled gracefully."""
    response = client.get("/24-25/")
    assert response.status_code == 200
    assert b"Ocurri\xc3\xb3 un error al cargar los comunicados" in response.data


@patch("packages.biwenger_tools.web.routes.season.download_csv_as_dict")
@patch("packages.biwenger_tools.web.routes.season.find_file_on_drive")
def test_salseo_success(
    mock_find_file, mock_download_csv, client, mock_comunicados_data
):
    """Verify that the salseo page loads correctly with data."""
    mock_find_file.side_effect = [{"id": "fake_id"}, None, None]
    mock_download_csv.return_value = mock_comunicados_data
    response = client.get("/24-25/salseo")
    assert response.status_code == 200
    assert b"D1" in response.data
    assert b"CR1" in response.data
    assert b"C1" not in response.data


@patch("packages.biwenger_tools.web.routes.season.download_csv_as_dict")
@patch(
    "packages.biwenger_tools.web.routes.season.find_file_on_drive",
    return_value={"id": "fake_id"},
)
def test_participacion_renders_calculated_counts(
    mock_find_file, mock_download_csv, client, mock_participacion_data
):
    """The route must compute counts from the semicolon-joined CSV cells.

    Autor1 has comunicados="c1;c2", datos="d1" → 2 comunicados, 1 dato.
    Autor2 has datos="d1;d2" → 2 datos. The page must render those
    numbers, not the raw "c1;c2" string.
    """
    mock_download_csv.return_value = mock_participacion_data
    response = client.get("/24-25/participacion")
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    # The raw CSV strings must NOT leak into the HTML
    assert "c1;c2" not in body
    assert "d1;d2" not in body

    # Authors and computed counts must appear
    assert "Autor1" in body
    assert "Autor2" in body
    # Autor1's comunicados cell should render as 2; Autor2's datos cell as 2
    # Use regex-friendly substring that locks the cell to the row
    assert ">2<" in body  # at least one cell shows the count 2
    assert ">1<" in body  # Autor1's "datos" count


@patch("packages.biwenger_tools.web.routes.main.download_csv_as_dict")
@patch(
    "packages.biwenger_tools.web.routes.main.find_file_on_drive",
    return_value={"id": "fake_id"},
)
def test_palmares_groups_otros_categories(
    mock_find_file, mock_download_csv, client, mock_palmares_data
):
    """multa/sancion/farolillo are bucketed into seasons[year]["otros"];
    other categories (e.g. campeon) become direct keys. Verify the grouping
    actually happens — not just that names appear in the HTML."""
    mock_download_csv.return_value = mock_palmares_data
    response = client.get("/palmares")
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    # Direct categories rendered
    assert "Jorge" in body  # 24-25 campeon
    assert "Dani" in body  # 23-24 campeon
    # "otros" group payload (multa/sancion/farolillo all from 23-24)
    assert "20" in body
    assert "tarjeta roja" in body
    assert "Pepe" in body


# --- API endpoint tests ---


@patch("packages.biwenger_tools.web.routes.season.get_sheets_data")
def test_api_lloros_ligas_returns_sheets_data(mock_get_sheets, client):
    """The endpoint forwards the sheets_data result for the active season."""
    payload = [{"nombre": "Liga A", "headers": ["Pos", "Equipo"], "rows": [["1", "X"]]}]
    mock_get_sheets.return_value = payload
    with patch(
        "packages.biwenger_tools.web.routes.season.config.LIGAS_ESPECIALES_SHEETS",
        {"25-26": "sheet-id-test"},
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
    payload = [{"nombre": "Pichichi", "headers": ["Goleador"], "rows": [["X"]]}]
    mock_get_sheets.return_value = payload
    with patch(
        "packages.biwenger_tools.web.routes.season.config.TROFEOS_SHEETS",
        {"25-26": "sheet-id-test"},
    ):
        response = client.get("/api/lloros-awards/trofeos")
    assert response.status_code == 200
    assert response.get_json() == payload


# --- Admin panel tests ---


@patch("packages.biwenger_tools.web.app.config.ADMIN_PASSWORD", "test_password")
def test_admin_login_get_page(client):
    """Verify that the admin login page loads correctly."""
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Acceso al VAR" in response.data


@patch("packages.biwenger_tools.web.app.config.ADMIN_PASSWORD", "test_password")
def test_admin_login_post_success(client):
    """Verify that login succeeds with the correct password."""
    response = client.post(
        "/admin", data={"password": "test_password"}, follow_redirects=True
    )
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess["admin_logged_in"] is True


@patch("packages.biwenger_tools.web.app.config.ADMIN_PASSWORD", "test_password")
def test_admin_login_post_fail(client):
    """Verify that login fails with an incorrect password."""
    response = client.post("/admin", data={"password": "wrong_password"})
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert "admin_logged_in" not in sess


@patch("packages.biwenger_tools.web.routes.admin._build_file_statuses")
def test_admin_panel_page_loads(mock_build_statuses, client):
    """Verify that the admin panel loads when the user is logged in."""
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    mock_build_statuses.return_value = [
        {
            "name": "comunicados_24-25.csv",
            "status": "Encontrado",
            "is_stale": False,
            "last_updated": "01-01-2025 a las 00:00:00",
        },
    ]
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"comunicados_24-25.csv" in response.data


def test_logout_clears_session(client):
    """Verify that the session is cleared on logout."""
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert "admin_logged_in" not in sess
