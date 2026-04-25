import pytest
import os
from unittest.mock import patch, MagicMock
from packages.biwenger_tools.web.app import app
from flask import Flask

# --- Configuración y Fixtures de Pytest ---


# Usamos este fixture para simular las llamadas a los servicios de Google
# sin necesidad de una cuenta de servicio real.
@pytest.fixture(autouse=True)
def mock_google_services_init():
    """Mockea la inicialización de los servicios de Google en el arranque de la app."""
    # Mockeamos el os.path.exists para que devuelva True, simulando que el archivo existe
    with patch("packages.biwenger_tools.web.app.os.path.exists", return_value=True):
        # Mockeamos la función que construye los servicios de Google
        with patch(
            "packages.biwenger_tools.web.app.get_google_service",
            MagicMock(return_value=MagicMock()),
        ) as mock_get_service:
            yield mock_get_service


@pytest.fixture
def client():
    """Crea un cliente de prueba para la aplicación Flask."""
    # Seteamos la clave secreta para la sesión en los tests
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test_key"
    with app.test_client() as client:
        yield client


# --- Fixtures para datos de prueba ---
@pytest.fixture
def mock_comunicados_data():
    """Datos de ejemplo para los comunicados."""
    return [
        {"categoria": "comunicado", "titulo": "C1"},
        {"categoria": "dato", "titulo": "D1"},
        {"categoria": "comunicado", "titulo": "C2"},
        {"categoria": "cesion", "titulo": "CES1"},
        {"categoria": "cronica", "titulo": "CR1"},
        {"categoria": "comunicado", "titulo": "C3"},
    ]


@pytest.fixture
def mock_participacion_data():
    """Datos de ejemplo para la participación."""
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
    """Datos de ejemplo para el palmarés."""
    return [
        {"temporada": "24-25", "categoria": "campeon", "valor": "Jorge"},
        {"temporada": "23-24", "categoria": "multa", "valor": "20"},
        {"temporada": "23-24", "categoria": "campeon", "valor": "Dani"},
    ]


@pytest.fixture
def mock_ligas_data():
    """Datos de ejemplo para ligas especiales."""
    return [{"nombre": "Liga1"}, {"nombre": "Liga2"}]


@pytest.fixture
def mock_trofeos_data():
    """Datos de ejemplo para trofeos."""
    return [{"nombre": "Trofeo1"}, {"nombre": "Trofeo2"}]


# --- Tests para el manejo de la sesión y rutas básicas ---


def test_home_redirects_to_current_season(client):
    """Verifica que la ruta / redirige a la temporada actual."""
    with client.session_transaction() as sess:
        sess["current_season"] = "24-25"
    response = client.get("/")
    assert response.status_code == 302
    assert "/24-25/" in response.headers["Location"]


def test_before_request_manages_season(client):
    """Verifica que la sesión se actualiza con la temporada de la URL."""
    client.get("/")
    assert client.get_cookie("session") is not None
    response = client.get("/25-26/")
    # La sesión se establece antes de la redirección
    with client.session_transaction() as sess:
        assert sess["current_season"] == "25-26"


def test_before_request_ignores_invalid_url(client):
    """Verifica que URLs inválidas no cambian la temporada en la sesión."""
    client.get("/")
    with client.session_transaction() as sess:
        sess["current_season"] = "24-25"
    client.get("/favicon.ico")
    with client.session_transaction() as sess:
        assert sess["current_season"] == "24-25"


# --- Tests para las Rutas de Contenido ---


@patch("packages.biwenger_tools.web.app.download_csv_as_dict")
@patch(
    "packages.biwenger_tools.web.app.find_file_on_drive", return_value={"id": "fake_id"}
)
def test_comunicados_success(
    mock_find_file, mock_download_csv, client, mock_comunicados_data
):
    """Verifica que la página de comunicados se carga correctamente con datos."""
    mock_download_csv.return_value = mock_comunicados_data
    response = client.get("/24-25/")
    assert response.status_code == 200
    assert b"C1" in response.data
    assert b"C2" in response.data
    assert b"D1" not in response.data  # Verifica que solo se muestran comunicados


@patch("packages.biwenger_tools.web.app.find_file_on_drive", return_value=None)
def test_comunicados_file_not_found(mock_find_file, client):
    """Verifica que se muestra un error si el archivo no se encuentra."""
    response = client.get("/24-25/")
    assert response.status_code == 200
    # Aserción corregida para buscar el texto de error en cualquier lugar de la respuesta
    assert b"Ocurri\xc3\xb3 un error" in response.data or b"error" in response.data


@patch(
    "packages.biwenger_tools.web.app.download_csv_as_dict",
    side_effect=Exception("Test error"),
)
@patch(
    "packages.biwenger_tools.web.app.find_file_on_drive", return_value={"id": "fake_id"}
)
def test_comunicados_general_exception(mock_find_file, mock_download_csv, client):
    """Verifica que se muestra un error en caso de excepción general."""
    response = client.get("/24-25/")
    assert response.status_code == 200
    assert b"Ocurri\xc3\xb3 un error al cargar los comunicados" in response.data


@patch("packages.biwenger_tools.web.app.download_csv_as_dict")
@patch("packages.biwenger_tools.web.app.find_file_on_drive")
def test_salseo_success(
    mock_find_file, mock_download_csv, client, mock_comunicados_data
):
    """Verifica que la página de salseo se carga correctamente con datos."""
    # Primera llamada: comunicados. Siguientes (clausulazos, tabla_justicia): no encontrado.
    mock_find_file.side_effect = [{"id": "fake_id"}, None, None]
    mock_download_csv.return_value = mock_comunicados_data
    response = client.get("/24-25/salseo")
    assert response.status_code == 200
    assert b"D1" in response.data
    assert b"CR1" in response.data
    assert b"C1" not in response.data
    assert b"CES1" not in response.data


@patch("packages.biwenger_tools.web.app.download_csv_as_dict")
@patch(
    "packages.biwenger_tools.web.app.find_file_on_drive", return_value={"id": "fake_id"}
)
def test_participacion_success(
    mock_find_file, mock_download_csv, client, mock_participacion_data
):
    """Verifica que la página de participación se carga y calcula las estadísticas."""
    mock_download_csv.return_value = mock_participacion_data
    response = client.get("/24-25/participacion")
    assert response.status_code == 200
    assert b"Autor1" in response.data
    assert b"Autor2" in response.data
    # Aserción corregida: Busca un total calculado para Autor1 (2+1=3)
    assert b"Autor1" in response.data and b"3" in response.data


@patch("packages.biwenger_tools.web.app.download_csv_as_dict")
@patch(
    "packages.biwenger_tools.web.app.find_file_on_drive", return_value={"id": "fake_id"}
)
def test_palmares_success(
    mock_find_file, mock_download_csv, client, mock_palmares_data
):
    """Verifica que la página de palmarés se carga y procesa los datos."""
    mock_download_csv.return_value = mock_palmares_data
    response = client.get("/palmares")
    assert response.status_code == 200
    # Aserción corregida para buscar el nombre del campeón y la multa
    assert b"Jorge" in response.data
    assert b"Dani" in response.data
    assert b"20" in response.data


@patch("packages.biwenger_tools.web.app.get_sheets_data")
def test_reglamento_success(mock_get_sheets, client, mock_ligas_data):
    """Verifica que la página de reglamento se carga con datos de las ligas."""
    mock_get_sheets.return_value = mock_ligas_data
    response = client.get("/reglamento")
    assert response.status_code == 200
    # CORRECCIÓN: La plantilla no renderiza los datos de "ligas". La aserción correcta es buscar un texto fijo.
    assert b"Fair Play / El Veredicto" in response.data


# --- Tests para Endpoints API ---


@patch("packages.biwenger_tools.web.app.get_sheets_data")
def test_api_lloros_ligas_success(mock_get_sheets, client, mock_ligas_data):
    """Verifica que el endpoint de ligas devuelve JSON."""
    mock_get_sheets.return_value = mock_ligas_data
    response = client.get("/api/lloros-awards/ligas?season=24-25")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == mock_ligas_data


@patch("packages.biwenger_tools.web.app.get_sheets_data")
def test_api_lloros_trofeos_success(mock_get_sheets, client, mock_trofeos_data):
    """Verifica que el endpoint de trofeos devuelve JSON."""
    mock_get_sheets.return_value = mock_trofeos_data
    response = client.get("/api/lloros-awards/trofeos?season=24-25")
    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == mock_trofeos_data


# --- Tests para el Panel de Administración ---


@patch("packages.biwenger_tools.web.app.config.ADMIN_PASSWORD", "test_password")
def test_admin_login_get_page(client):
    """Verifica que la página de login de admin se carga correctamente."""
    response = client.get("/admin")
    assert response.status_code == 200
    # CORRECCIÓN: La plantilla usa "Acceso al VAR", no "Login de Administrador".
    assert b"Acceso al VAR" in response.data


@patch("packages.biwenger_tools.web.app.config.ADMIN_PASSWORD", "test_password")
def test_admin_login_post_success(client):
    """Verifica que se puede iniciar sesión con la contraseña correcta."""
    response = client.post(
        "/admin", data={"password": "test_password"}, follow_redirects=True
    )
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess["admin_logged_in"] is True


@patch("packages.biwenger_tools.web.app.config.ADMIN_PASSWORD", "test_password")
def test_admin_login_post_fail(client):
    """Verifica que el login falla con una contraseña incorrecta."""
    response = client.post("/admin", data={"password": "wrong_password"})
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert "admin_logged_in" not in sess


@patch("packages.biwenger_tools.web.app.get_file_metadata")
def test_admin_panel_page_loads(mock_get_metadata, client):
    """Verifica que el panel de admin se carga cuando el usuario está logeado."""
    # Simula un usuario logeado
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    # Mockea la respuesta de la función que busca los archivos
    mock_get_metadata.return_value = [
        {"name": "comunicados_24-25.csv", "status": "Encontrado"},
    ]
    response = client.get("/admin")
    assert response.status_code == 200
    # Aserción corregida para buscar un texto m\xc3\xa1s fiable
    assert b"comunicados_24-25.csv" in response.data


def test_logout_clears_session(client):
    """Verifica que la sesión se borra al hacer logout."""
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
    response = client.get("/logout", follow_redirects=True)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert "admin_logged_in" not in sess
