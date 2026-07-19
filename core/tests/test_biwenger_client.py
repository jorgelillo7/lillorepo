import pytest
import requests
import requests_mock

from core.sdk.biwenger import BiwengerError, BiwengerClient

from .constants import (
    TEST_ACCOUNT_URL,
    TEST_EMAIL,
    TEST_LEAGUE_ID,
    TEST_LEAGUE_USERS_URL,
    TEST_LOGIN_URL,
    TEST_MANAGER_SQUAD_URL_TEMPLATE,
    TEST_MARKET_URL,
    TEST_OFFERS_URL,
    TEST_PASSWORD,
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
    """Parses the standings into id→name and drops NON_PLAYING_MEMBER_IDS —
    the fixture includes the cronista (13945871), which must not appear."""
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
        assert 13945871 not in user_map


def test_get_league_users_include_non_playing(
    biwenger_client_authenticated, load_json_fixture
):
    """The scraper needs the full map — author resolution and participación
    must still see the cronista."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        mock_response = load_json_fixture("league_users.json")
        m.get(TEST_LEAGUE_USERS_URL, json=mock_response, status_code=200)

        user_map = client.get_league_users(
            TEST_LEAGUE_USERS_URL, include_non_playing=True
        )
        assert user_map[13945871] == "Reportajes Lloriquin"
        assert len(user_map) == 4


def test_authentication_raises_when_login_returns_no_token():
    """Login response without a token field must raise; we don't want to silently
    proceed with an unauthenticated session."""
    with requests_mock.Mocker() as m:
        m.post(TEST_LOGIN_URL, json={"foo": "bar"}, status_code=200)
        with pytest.raises(BiwengerError, match="no token received"):
            BiwengerClient(
                TEST_EMAIL,
                TEST_PASSWORD,
                TEST_LOGIN_URL,
                TEST_ACCOUNT_URL,
                TEST_LEAGUE_ID,
            )


def test_authentication_raises_when_user_not_in_league(load_json_fixture):
    """If the requested league_id is not in the account response, raise — the
    rest of the client assumes self.user_id is set."""
    with requests_mock.Mocker() as m:
        login_data = load_json_fixture("login_response.json")
        m.post(TEST_LOGIN_URL, json=login_data, status_code=200)
        # Account response with a different league_id than TEST_LEAGUE_ID
        m.get(
            TEST_ACCOUNT_URL,
            json={"data": {"leagues": [{"id": "999999", "user": {"id": 1}}]}},
            status_code=200,
        )
        with pytest.raises(BiwengerError, match="Could not find user ID for league"):
            BiwengerClient(
                TEST_EMAIL,
                TEST_PASSWORD,
                TEST_LOGIN_URL,
                TEST_ACCOUNT_URL,
                TEST_LEAGUE_ID,
            )


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


def test_get_account_state_cash_only(biwenger_client_authenticated, load_json_fixture):
    """Without squad+all_players, only cash is returned (max_bid=0)."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.get(TEST_ACCOUNT_URL, json=load_json_fixture("account_response.json"))
        state = client.get_account_state()
    assert state == {"cash": 10_000_000, "max_bid": 0}


def test_get_account_state_computes_max_bid_with_squad_and_prices(
    biwenger_client_authenticated, load_json_fixture
):
    """max_bid = cash + 25% of squad_value (sum of player.price).

    Verified empirically against Biwenger's displayed "Puja máxima":
    12,972,212 € cash + 25% * 93,450,000 € squad = 36,334,712 € (matches
    Biwenger UI to the euro).
    """
    client = biwenger_client_authenticated
    squad = [{"id": 1}, {"id": 2}, {"id": 3}]
    all_players = {
        1: {"price": 20_000_000},
        2: {"price": 10_000_000},
        3: {"price": 5_000_000},
    }
    with requests_mock.Mocker() as m:
        m.get(TEST_ACCOUNT_URL, json=load_json_fixture("account_response.json"))
        state = client.get_account_state(squad=squad, all_players=all_players)
    # 35M squad value * 25% = 8.75M; cash 10M -> max_bid 18.75M
    assert state["cash"] == 10_000_000
    assert state["max_bid"] == 18_750_000


def test_get_account_state_handles_missing_prices(
    biwenger_client_authenticated, load_json_fixture
):
    """Players not present in all_players don't crash; they contribute 0."""
    client = biwenger_client_authenticated
    squad = [{"id": 1}, {"id": 999}]  # 999 not in lookup
    all_players = {1: {"price": 4_000_000}}
    with requests_mock.Mocker() as m:
        m.get(TEST_ACCOUNT_URL, json=load_json_fixture("account_response.json"))
        state = client.get_account_state(squad=squad, all_players=all_players)
    assert state["max_bid"] == 10_000_000 + 4_000_000 // 4  # cash + 1M


# --- place_market_bid ---


def test_place_market_bid_posts_offer_with_expected_body(
    biwenger_client_authenticated,
):
    """Body shape must be {to: null, type: "purchase", amount, requestedPlayers:[id]}.

    `to=None` is the marker for daily-market players (computer-owned);
    deviating from that shape would route the bid as a user-to-user offer.
    """
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(
            TEST_OFFERS_URL,
            json={
                "status": 200,
                "data": {
                    "fromID": 1,
                    "toID": None,
                    "type": "purchase",
                    "amount": 8_480_000,
                    "id": 99,
                    "status": "waiting",
                },
            },
            status_code=200,
        )
        data = client.place_market_bid(
            player_id=20102, amount=8_480_000, offers_url=TEST_OFFERS_URL
        )

    assert data["id"] == 99
    assert data["status"] == "waiting"
    assert m.last_request.json() == {
        "to": None,
        "type": "purchase",
        "amount": 8_480_000,
        "requestedPlayers": [20102],
    }


def test_place_clausulazo_posts_offer_with_expected_body(
    biwenger_client_authenticated,
):
    """Clausulazo body shape: same `/offers` endpoint as bids, but
    `to=<seller_user_id>` (the current owner) and `type="clause"`.

    Response shape mirrors `place_market_bid` (data block has `fromID`,
    `toID`, `amount`, `type`, `status`, `id`).
    """
    client = biwenger_client_authenticated
    captured_response = {
        "status": 200,
        "data": {
            "fromID": 1372802,
            "type": "clause",
            "amount": 1_420_004,
            "created": 1779822946,
            "modified": 1779822946,
            "status": "processed",
            "toID": 12449616,
            "id": 1505330715,
        },
    }
    with requests_mock.Mocker() as m:
        m.post(TEST_OFFERS_URL, json=captured_response, status_code=200)
        data = client.place_clausulazo(
            player_id=99999,
            amount=1_420_004,
            seller_user_id=12449616,
            offers_url=TEST_OFFERS_URL,
        )

    assert data["id"] == 1505330715
    assert data["status"] == "processed"
    assert data["type"] == "clause"
    assert m.last_request.json() == {
        "to": 12449616,
        "type": "clause",
        "amount": 1_420_004,
        "requestedPlayers": [99999],
    }


def test_place_clausulazo_coerces_numeric_args_to_int(biwenger_client_authenticated):
    """Coerce any numeric input to plain int — Biwenger 400s on floats."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_OFFERS_URL, json={"data": {}}, status_code=200)
        client.place_clausulazo(
            player_id="99999",  # type: ignore[arg-type]
            amount=1_420_004.0,  # type: ignore[arg-type]
            seller_user_id="12449616",  # type: ignore[arg-type]
            offers_url=TEST_OFFERS_URL,
        )
    body = m.last_request.json()
    assert body == {
        "to": 12449616,
        "type": "clause",
        "amount": 1_420_004,
        "requestedPlayers": [99999],
    }


def test_place_market_bid_coerces_numeric_args_to_int(biwenger_client_authenticated):
    """Callers may pass numpy ints, floats from intermediate maths, etc.; the
    payload must always serialise as plain ints (Biwenger 400s on floats)."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_OFFERS_URL, json={"data": {}}, status_code=200)
        client.place_market_bid(
            player_id="20102",  # type: ignore[arg-type]
            amount=8_480_000.0,  # type: ignore[arg-type]
            offers_url=TEST_OFFERS_URL,
        )
    body = m.last_request.json()
    assert body["amount"] == 8_480_000
    assert body["requestedPlayers"] == [20102]
    assert isinstance(body["amount"], int)
    assert isinstance(body["requestedPlayers"][0], int)


def test_place_market_bid_raises_on_4xx(biwenger_client_authenticated):
    """Biwenger returns 4xx when a higher bid already locked the player or
    the offer is otherwise rejected. The SDK surfaces the error so the
    caller can log + continue with the next candidate."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_OFFERS_URL, status_code=409, text="conflict")
        with pytest.raises(requests.HTTPError):
            client.place_market_bid(
                player_id=1, amount=1_000_000, offers_url=TEST_OFFERS_URL
            )


def test_place_market_bid_returns_empty_dict_when_data_missing(
    biwenger_client_authenticated,
):
    """Defensive: if Biwenger returns 200 with no `data` field we still
    return an empty dict instead of None so the caller can `.get("id")`."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_OFFERS_URL, json={"status": 200}, status_code=200)
        data = client.place_market_bid(
            player_id=1, amount=1, offers_url=TEST_OFFERS_URL
        )
    assert data == {}


def test_get_account_state_unknown_league_returns_zeros(
    biwenger_client_authenticated, load_json_fixture
):
    """When the league_id isn't found in the response, both fields are 0."""
    client = biwenger_client_authenticated
    client.league_id = "doesnotexist"
    with requests_mock.Mocker() as m:
        m.get(TEST_ACCOUNT_URL, json=load_json_fixture("account_response.json"))
        state = client.get_account_state()
    assert state == {"cash": 0, "max_bid": 0}


def test_get_report_rows_parses_columns_and_rows(biwenger_client_authenticated):
    """report/* endpoints return {columns, rows}; the SDK zips them into dicts
    keyed by column name so callers can pull values by the label the UI uses."""
    url = "https://biwenger.as.com/api/v2/league/340703/report/rounds?mode=total"
    payload = {
        "status": 200,
        "data": {
            "columns": [
                {"name": "Usuario", "type": "user"},
                {"name": "Jornadas ganadas", "type": "number"},
                {"name": "Posición media", "type": "ordinal"},
            ],
            "rows": [
                [{"id": 7728610, "name": "Rayo Entrebirras"}, "11", 2.8],
                [{"id": 1372802, "name": "Farolillo Oracle United"}, "3", 3.8],
            ],
        },
    }
    with requests_mock.Mocker() as m:
        m.get(url, json=payload, status_code=200)
        rows = biwenger_client_authenticated.get_report_rows(url)
    assert len(rows) == 2
    assert rows[0]["Usuario"]["id"] == 7728610
    assert rows[0]["Jornadas ganadas"] == "11"
    assert rows[0]["Posición media"] == 2.8
    assert rows[1]["Usuario"]["name"] == "Farolillo Oracle United"


def test_get_report_rows_empty_payload(biwenger_client_authenticated):
    """Missing columns/rows → empty list, no exception."""
    url = "https://biwenger.as.com/api/v2/league/340703/report/roundPoints?mode=total"
    with requests_mock.Mocker() as m:
        m.get(url, json={"status": 200, "data": {}}, status_code=200)
        rows = biwenger_client_authenticated.get_report_rows(url)
    assert rows == []
