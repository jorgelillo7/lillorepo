import requests_mock

from .constants import (
    TEST_BOARD_URL,
    TEST_LEAGUE_USERS_URL,
    TEST_MANAGER_SQUAD_URL_TEMPLATE,
    TEST_MARKET_URL,
    TEST_PLAYERS_DATA_URL,
)


def test_authentication_success(biwenger_client_authenticated):
    """
    Verifica que el cliente se autentica correctamente y obtiene el user_id.
    El fixture 'biwenger_client_authenticated' ya realiza la autenticación,
    por lo que solo se necesitan las aserciones.
    """
    client = biwenger_client_authenticated
    assert client.user_id == 98765
    assert client.session.headers["X-League"] == "123456"
    assert client.session.headers["X-User"] == "98765"


def test_get_league_users(biwenger_client_authenticated, load_json_fixture):
    """Verifica que get_league_users parsea correctamente la respuesta de la API."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        # Carga la respuesta de usuarios desde el archivo JSON
        mock_response = load_json_fixture("league_users.json")
        m.get(TEST_LEAGUE_USERS_URL, json=mock_response, status_code=200)

        user_map = client.get_league_users(TEST_LEAGUE_USERS_URL)
        expected_map = {
            1: "Farolillo Oracle United",
            2: "Rayo Entrebirras",
            3: "#NOALOSCLAUSULAZOS",
        }
        assert user_map == expected_map
        assert len(user_map) == 3


def test_get_board_messages(biwenger_client_authenticated, load_json_fixture):
    """Verifica que get_board_messages devuelve los datos del tablón."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        mock_response = load_json_fixture("board_messages.json")
        m.get(TEST_BOARD_URL, json=mock_response, status_code=200)

        messages = client.get_board_messages(TEST_BOARD_URL)
        assert messages["data"]["messages"][0]["text"] == "¡Bienvenidos a la liga!"
        assert messages["data"]["messages"][0]["author"] == "Farolillo Oracle United"


def test_get_all_players_data_map_json(
    biwenger_client_authenticated, load_json_fixture
):
    """Verifica que el método procesa una respuesta JSON de jugadores."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        # Carga la respuesta de jugadores desde el archivo JSON
        players_data = load_json_fixture("all_players_data.json")
        m.get(TEST_PLAYERS_DATA_URL, json=players_data, status_code=200)

        players_map = client.get_all_players_data_map(TEST_PLAYERS_DATA_URL)
        assert len(players_map) == 2
        assert players_map[1001]["name"] == "Yamal"


def test_get_all_players_data_map_jsonp(biwenger_client_authenticated):
    """Verifica que el método procesa una respuesta JSONP."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        jsonp_string = (
            'jsonp_12345({"data": {"players": '
            '{"3": {"id": 3, "name": "Mbappé", "teamId": 3}}}}) '
        )
        m.get(TEST_PLAYERS_DATA_URL, text=jsonp_string, status_code=200)

        players_map = client.get_all_players_data_map(TEST_PLAYERS_DATA_URL)
        expected_map = {3: {"id": 3, "name": "Mbappé", "teamId": 3}}
        assert players_map == expected_map
        assert len(players_map) == 1


def test_get_manager_squad(biwenger_client_authenticated, load_json_fixture):
    """Verifica que get_manager_squad devuelve la plantilla del mánager."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        # Carga la respuesta de la plantilla desde el archivo JSON
        mock_response = load_json_fixture("manager_squad.json")
        m.get(TEST_MANAGER_SQUAD_URL_TEMPLATE.format(manager_id=1), json=mock_response)

        squad = client.get_manager_squad(TEST_MANAGER_SQUAD_URL_TEMPLATE, 1)
        assert len(squad) == 2
        assert squad[0]["name"] == "Yamal"
        assert squad[1]["id"] == 1002


def test_get_market_players(biwenger_client_authenticated, load_json_fixture):
    """Verifica que el método procesa correctamente una respuesta del mercado."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        # Carga la respuesta del mercado desde el archivo JSON
        mock_response = load_json_fixture("market_players.json")
        m.get(TEST_MARKET_URL, json=mock_response, status_code=200)

        market_players = client.get_market_players(TEST_MARKET_URL)
        expected_list = [
            {"id": 2001, "name": "Yamal", "price": 20000000},
            {"id": 2002, "name": "Isco", "price": 7000000},
        ]
        assert market_players == expected_list
        assert len(market_players) == 2


# --- Paginators ---


def test_get_all_board_messages_single_page(biwenger_client_authenticated):
    """Single response shorter than `limit` ends pagination."""
    client = biwenger_client_authenticated
    client.get_board_messages = lambda url: {"data": [{"id": 1}, {"id": 2}, {"id": 3}]}
    seen_urls = []
    original = client.get_board_messages

    def spy(url):
        seen_urls.append(url)
        return original(url)

    client.get_board_messages = spy
    messages = client.get_all_board_messages("http://test.com")
    assert len(messages) == 3
    assert seen_urls == ["http://test.com&limit=200&offset=0"]


def test_get_all_board_messages_paginates(biwenger_client_authenticated):
    """Stops once a page is shorter than `limit`."""
    client = biwenger_client_authenticated
    pages = [
        {"data": [{"id": i} for i in range(200)]},
        {"data": [{"id": i} for i in range(200, 250)]},
        {"data": []},
    ]
    seen_urls = []

    def stub(url):
        seen_urls.append(url)
        return pages.pop(0)

    client.get_board_messages = stub
    messages = client.get_all_board_messages("http://test.com")
    assert len(messages) == 250
    assert seen_urls == [
        "http://test.com&limit=200&offset=0",
        "http://test.com&limit=200&offset=200",
    ]


def test_get_all_clausulazos_paginates(biwenger_client_authenticated):
    """Aggregates pages and returns a `{'data': [...]}` envelope."""
    client = biwenger_client_authenticated
    pages = [
        {"data": [{"date": i} for i in range(200)]},
        {"data": [{"date": i} for i in range(50)]},
    ]
    client.get_clausulazos = lambda url: pages.pop(0)
    result = client.get_all_clausulazos("http://api/board?type=transfer")
    assert len(result["data"]) == 250
    assert pages == []


def test_get_all_clausulazos_stops_on_empty(biwenger_client_authenticated):
    """Empty first response yields `{'data': []}`."""
    client = biwenger_client_authenticated
    calls = []

    def stub(url):
        calls.append(url)
        return {"data": []}

    client.get_clausulazos = stub
    result = client.get_all_clausulazos("http://api/board?type=transfer")
    assert result == {"data": []}
    assert len(calls) == 1
