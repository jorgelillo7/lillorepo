from unittest.mock import patch

import pytest
import requests
import requests_mock

from core.sdk.biwenger import (
    BiwengerError,
    BiwengerClient,
    admin_transfers_url,
    clausulazos_url,
    league_board_url,
)

from .constants import (
    TEST_ACCOUNT_URL,
    TEST_EMAIL,
    TEST_LEAGUE_ID,
    TEST_LEAGUE_USERS_URL,
    TEST_LINEUP_URL,
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
    """Parses the standings into id→name and drops every excluded id — the
    fixture includes an account (13945871) the caller asks to leave out."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        # Carga la respuesta de usuarios desde el archivo JSON
        mock_response = load_json_fixture("league_users.json")
        m.get(TEST_LEAGUE_USERS_URL, json=mock_response, status_code=200)

        user_map = client.get_league_users(TEST_LEAGUE_USERS_URL, frozenset({13945871}))
        expected_map = {
            1: "Farolillo Oracle United",
            2: "Rayo Entrebirras",
            3: "#NOALOSCLAUSULAZOS",
        }
        assert user_map == expected_map
        assert 13945871 not in user_map


def test_get_league_users_excluding_nobody_returns_everyone(
    biwenger_client_authenticated, load_json_fixture
):
    """The scraper needs the full map — author resolution and participación
    must still see accounts that do not compete."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        mock_response = load_json_fixture("league_users.json")
        m.get(TEST_LEAGUE_USERS_URL, json=mock_response, status_code=200)

        user_map = client.get_league_users(TEST_LEAGUE_USERS_URL, frozenset())
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


def test_get_competition_maps_downloads_once(load_json_fixture):
    """Both maps come from a single request, and without a session.

    Asking for players and teams separately pulled the same ~550-player
    payload twice per market load; the endpoint is public, so no login is
    needed either.
    """
    with requests_mock.Mocker() as m:
        m.get(
            TEST_PLAYERS_DATA_URL,
            json=load_json_fixture("all_players_data.json"),
            status_code=200,
        )

        players_map, teams_map = BiwengerClient.get_competition_maps(
            TEST_PLAYERS_DATA_URL
        )

        assert m.call_count == 1
        assert players_map[1001]["name"] == "Yamal"
        assert isinstance(teams_map, dict)


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


def test_get_market_players_when_the_market_is_disabled(biwenger_client_authenticated):
    """A closed market answers 200 with a null payload, not an empty list.

    `.get("data", {})` returns None for a key that is present and null — the
    default only fires when the key is missing — so chaining `.get("sales")`
    off it raised AttributeError and turned `/teams` into a 500 after every
    squad photo had already been delivered.
    """
    client = biwenger_client_authenticated
    for payload in ({"data": None}, {"data": {"sales": None}}, {}):
        with requests_mock.Mocker() as m:
            m.get(TEST_MARKET_URL, json=payload, status_code=200)
            assert client.get_market_players(TEST_MARKET_URL) == []


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


# --- transfer_player / revert_transfer / apply_bonus ---

TEST_TRANSFER_URL = "https://biwenger.as.com/api/v2/league/123456/transfer"
TEST_BONUS_URL = "https://biwenger.as.com/api/v2/league/123456/bonus"


def test_transfer_player_posts_expected_body_and_url(biwenger_client_authenticated):
    """Body shape must be {to, amount, player, operation: "transfer"};
    `to=0` is the free-agency marker so it must round-trip untouched."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_TRANSFER_URL, status_code=204)
        result = client.transfer_player(
            player_id=20102, manager_id=0, amount=10_000_000
        )

    assert result is None
    assert m.last_request.url == TEST_TRANSFER_URL
    assert m.last_request.json() == {
        "to": 0,
        "amount": 10_000_000,
        "player": 20102,
        "operation": "transfer",
    }


def test_transfer_player_coerces_numeric_args_to_int(biwenger_client_authenticated):
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_TRANSFER_URL, status_code=204)
        client.transfer_player(
            player_id="20102",  # type: ignore[arg-type]
            manager_id="7728610",  # type: ignore[arg-type]
            amount=10_000_000.0,  # type: ignore[arg-type]
        )
    body = m.last_request.json()
    assert body == {
        "to": 7728610,
        "amount": 10_000_000,
        "player": 20102,
        "operation": "transfer",
    }


def test_transfer_player_not_retried_on_failure(biwenger_client_authenticated):
    """A 500 must NOT be retried — a retried transfer would double-assign
    the player and double-charge the manager."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_TRANSFER_URL, status_code=500, text="boom")
        with pytest.raises(requests.HTTPError):
            client.transfer_player(player_id=1, manager_id=2, amount=1_000_000)
    assert m.call_count == 1


def test_revert_transfer_posts_expected_body(biwenger_client_authenticated):
    """Body shape must be {to: 0, amount, player, offer, operation:
    "revertOffer"} — `amount` is the SAME positive value as the original
    transfer, and `offer` references it."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_TRANSFER_URL, status_code=204)
        result = client.revert_transfer(
            player_id=20102, amount=10_000_000, offer_id=555
        )

    assert result is None
    assert m.last_request.json() == {
        "to": 0,
        "amount": 10_000_000,
        "player": 20102,
        "offer": 555,
        "operation": "revertOffer",
    }


def test_revert_transfer_not_retried_on_failure(biwenger_client_authenticated):
    """Same non-idempotency risk as `transfer_player`: no retry on failure."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_TRANSFER_URL, status_code=503, text="unavailable")
        with pytest.raises(requests.HTTPError):
            client.revert_transfer(player_id=1, amount=1_000_000, offer_id=1)
    assert m.call_count == 1


def test_apply_bonus_posts_expected_body(biwenger_client_authenticated):
    """Body shape must be {amount: {user_id: signed_delta, ...}, reason}.
    The full league member map is sent, 0 for untouched managers."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_BONUS_URL, status_code=204)
        result = client.apply_bonus(
            amounts={1372802: -5_000_000, 7728610: 0, 12449616: 5_000_000},
            reason="Penalización por alineación indebida",
        )

    assert result is None
    assert m.last_request.json() == {
        "amount": {"1372802": -5_000_000, "7728610": 0, "12449616": 5_000_000},
        "reason": "Penalización por alineación indebida",
    }


def test_apply_bonus_not_retried_on_failure(biwenger_client_authenticated):
    """A failing bonus POST must NOT be retried — a retry would apply
    every manager's delta twice."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_BONUS_URL, status_code=500, text="boom")
        with pytest.raises(requests.HTTPError):
            client.apply_bonus(amounts={1: -1_000_000}, reason="test")
    assert m.call_count == 1


# ---------------------------------------------------------------------------
# The write path — the calls that move money or decide how the squad plays.
#
# Every test below covers something that had no test at all, or a retry
# stance stated only in a docstring. The distinction they pin is the one
# that costs money if it drifts: reads and idempotent writes retry, admin
# mutations must not, because Biwenger answers them 204 with no body and no
# idempotency key.
# ---------------------------------------------------------------------------


def _no_backoff():
    """Skip `retry_http_request`'s real sleeps (2 + 5 + 10 s)."""
    return patch("core.sdk.http.time.sleep")


def test_set_lineup_sends_the_formation_starters_reserves_and_captain(
    biwenger_client_authenticated,
):
    """The only call that writes the XI. Biwenger reads `playersID` and
    `reservesID` positionally, so their order is part of the contract."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.put(TEST_LINEUP_URL, json={"status": 200}, status_code=200)

        client.set_lineup(
            TEST_LINEUP_URL,
            formation="4-4-2",
            players_id=[1, 2, 3],
            reserves_id=[7, 8],
            captain=3,
        )

    assert m.last_request.json() == {
        "lineup": {
            "type": "4-4-2",
            "playersID": [1, 2, 3],
            "reservesID": [7, 8],
            "captain": 3,
        }
    }


@pytest.mark.parametrize("captain", [None, 0])
def test_set_lineup_sends_zero_when_no_starter_can_wear_the_armband(
    biwenger_client_authenticated, captain
):
    """No starter under the 3M MV cap must still apply the lineup. Biwenger
    spells "no captain" as 0; sending null would reject the whole payload and
    the squad would keep yesterday's XI."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.put(TEST_LINEUP_URL, json={"status": 200}, status_code=200)

        client.set_lineup(
            TEST_LINEUP_URL,
            formation="4-4-2",
            players_id=[1],
            reserves_id=[],
            captain=captain,
        )

    assert m.last_request.json()["lineup"]["captain"] == 0


def test_set_lineup_retries_a_transient_failure(biwenger_client_authenticated):
    """A Biwenger 5xx at 09:00 must not cost the matchday. The retry is the
    difference between a lineup applied and a squad left as it was."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m, _no_backoff():
        m.put(
            TEST_LINEUP_URL,
            [{"status_code": 502}, {"json": {"status": 200}, "status_code": 200}],
        )

        result = client.set_lineup(
            TEST_LINEUP_URL,
            formation="4-4-2",
            players_id=[1],
            reserves_id=[],
            captain=1,
        )

    assert result == {"status": 200}
    assert m.call_count == 2


def test_set_lineup_does_not_retry_a_payload_biwenger_refused(
    biwenger_client_authenticated,
):
    """A 4xx means the payload is wrong (invalid captain, bad formation).
    Retrying it just fails three more times and delays the error."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m, _no_backoff():
        m.put(TEST_LINEUP_URL, status_code=403, json={"message": "Invalid captain"})

        with pytest.raises(requests.HTTPError):
            client.set_lineup(
                TEST_LINEUP_URL,
                formation="4-4-2",
                players_id=[1],
                reserves_id=[],
                captain=1,
            )

    assert m.call_count == 1


def test_decide_offer_refuses_a_decision_biwenger_does_not_understand(
    biwenger_client_authenticated,
):
    """Guard before the request, not after: an unknown verb must never reach
    the API, where its meaning would be Biwenger's guess rather than ours."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        with pytest.raises(ValueError):
            client.decide_offer(1, "maybe", offers_url=TEST_OFFERS_URL)

    assert m.call_count == 0


def test_decide_offer_puts_the_decision_to_the_offer_and_returns_its_data(
    biwenger_client_authenticated,
):
    """The id goes in the path, the verdict in the body."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.put(
            f"{TEST_OFFERS_URL}/42",
            json={"status": 200, "data": {"id": 42, "status": "processed"}},
        )

        data = client.decide_offer(42, "accepted", offers_url=TEST_OFFERS_URL)

    assert m.last_request.json() == {"status": "accepted"}
    assert data == {"id": 42, "status": "processed"}


def test_decide_offer_returns_the_status_biwenger_settled_on(
    biwenger_client_authenticated,
):
    """What the caller asked for and what happened are different things: an
    accept comes back `processed` once Biwenger has executed the transfer.
    The confirmation sent to the chat must quote the settled status."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.put(
            f"{TEST_OFFERS_URL}/7",
            json={"status": 200, "data": {"id": 7, "status": "rejected"}},
        )

        data = client.decide_offer(7, "rejected", offers_url=TEST_OFFERS_URL)

    assert data["status"] == "rejected"


def test_decide_offer_raises_when_biwenger_refuses(biwenger_client_authenticated):
    """An offer already withdrawn or decided elsewhere must surface, not be
    reported to the user as done."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.put(f"{TEST_OFFERS_URL}/9", status_code=404)

        with pytest.raises(requests.HTTPError):
            client.decide_offer(9, "accepted", offers_url=TEST_OFFERS_URL)


def test_place_market_bid_retries_a_transient_failure(biwenger_client_authenticated):
    """The retry is why auto-bid does not lose a bid it already decided to
    place. Nothing pinned it before — deleting the wrapper broke no test."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m, _no_backoff():
        m.post(
            TEST_OFFERS_URL,
            [
                {"status_code": 500},
                {"json": {"data": {"id": 1, "status": "pending"}}, "status_code": 200},
            ],
        )

        data = client.place_market_bid(
            player_id=10, amount=5_000_000, offers_url=TEST_OFFERS_URL
        )

    assert data == {"id": 1, "status": "pending"}
    assert m.call_count == 2


def test_place_clausulazo_retries_a_transient_failure(biwenger_client_authenticated):
    """Same stance as the market bid: the clause window is short, and a 5xx
    inside it is a lost buyout rather than a refused one."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m, _no_backoff():
        m.post(
            TEST_OFFERS_URL,
            [
                {"status_code": 503},
                {
                    "json": {"data": {"id": 2, "status": "processed"}},
                    "status_code": 200,
                },
            ],
        )

        data = client.place_clausulazo(
            player_id=10,
            amount=9_000_000,
            seller_user_id=5,
            offers_url=TEST_OFFERS_URL,
        )

    assert data == {"id": 2, "status": "processed"}
    assert m.call_count == 2


def test_release_player_moves_no_money(biwenger_client_authenticated):
    """The undo path for a transfer we made ourselves. `amount: 0` is the
    whole safety property — a non-zero value here charges somebody for a
    player being taken away from them."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.post(TEST_TRANSFER_URL, status_code=204)

        client.release_player(player_id=77, transfer_url=TEST_TRANSFER_URL)

    assert m.last_request.json() == {
        "to": 0,
        "amount": 0,
        "player": 77,
        "operation": "transfer",
    }


def test_release_player_does_not_retry(biwenger_client_authenticated):
    """Admin mutations answer 204 with an empty body and carry no idempotency
    key, so a retry after a lost response applies the operation twice. One
    attempt, then the error — the caller re-reads Biwenger to find out what
    actually happened."""
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m, _no_backoff():
        m.post(TEST_TRANSFER_URL, status_code=500)

        with pytest.raises(requests.HTTPError):
            client.release_player(player_id=77, transfer_url=TEST_TRANSFER_URL)

    assert m.call_count == 1


# --- read-path gaps the spec had flagged ---------------------------------
#
# Biwenger answers `{"data": null}` when it has nothing to say — a closed
# market, a league mid-maintenance. Every reader below already defends against
# it; only two of them proved it. A maintenance window exercises all of them at
# once, which is the worst moment to find out.

TEST_STANDINGS_URL = "http://api.biwenger.com/league/123456?fields=standings"
TEST_USER_OFFERS_URL = "http://api.biwenger.com/user?fields=offers"
TEST_USER_LINEUP_URL = "http://api.biwenger.com/user?fields=lineup"


@pytest.mark.parametrize(
    "url, call, empty",
    [
        (
            TEST_LEAGUE_USERS_URL,
            lambda c, u: c.get_league_users(u, frozenset()),
            {},
        ),
        (TEST_STANDINGS_URL, lambda c, u: c.get_standings_full(u), []),
        (
            TEST_MANAGER_SQUAD_URL_TEMPLATE.format(manager_id=42),
            lambda c, _: c.get_manager_squad(TEST_MANAGER_SQUAD_URL_TEMPLATE, 42),
            [],
        ),
        (TEST_USER_OFFERS_URL, lambda c, u: c.get_received_offers(u), []),
        (
            TEST_USER_LINEUP_URL,
            lambda c, u: c.get_current_lineup_player_ids(u),
            set(),
        ),
    ],
)
def test_a_null_envelope_reads_as_empty_not_as_a_crash(
    biwenger_client_authenticated, url, call, empty
):
    with requests_mock.Mocker() as m:
        m.get(url, json={"status": 200, "data": None}, status_code=200)
        assert call(biwenger_client_authenticated, url) == empty


def test_get_standings_full_returns_the_table_in_order(biwenger_client_authenticated):
    """The palmarés and the season rollover read this and nothing tested it."""
    payload = {
        "status": 200,
        "data": {
            "standings": [
                {"position": 1, "name": "Farolillo Oracle United", "points": 1420},
                {"position": 2, "name": "Los Lloros CF", "points": 1388},
            ]
        },
    }
    with requests_mock.Mocker() as m:
        m.get(TEST_STANDINGS_URL, json=payload, status_code=200)
        standings = biwenger_client_authenticated.get_standings_full(TEST_STANDINGS_URL)
    # Biwenger's own order is the ranking; the SDK must not re-sort it.
    assert [row["position"] for row in standings] == [1, 2]
    assert standings[0]["name"] == "Farolillo Oracle United"
    assert standings[1]["points"] == 1388


def test_get_all_clausulazos_accepts_a_dict_shaped_page(
    biwenger_client_authenticated,
):
    """`data` as a dict, values taken in order.

    Pinned rather than removed: no test produced this shape, but nobody has
    established that Biwenger never sends it either, and a defence that only
    fires during a format change is exactly the one you cannot delete on a
    hunch. If a feed is ever seen returning it, name the feed here.
    """
    base = "http://api.biwenger.com/league/123456/board?type=transfer"
    client = biwenger_client_authenticated
    with requests_mock.Mocker() as m:
        m.get(
            f"{base}&limit=50&offset=0",
            json={"data": {"a": {"id": 1}, "b": {"id": 2}}},
            status_code=200,
        )
        m.get(f"{base}&limit=50&offset=50", json={"data": []}, status_code=200)
        result = client.get_all_clausulazos(base, limit=50)
    assert result == {"data": [{"id": 1}, {"id": 2}]}


# --- board feeds are chosen by `type`, and the wrong one fails silently ---
#
# A mismatched type returns 200 and an empty list, indistinguishable from a
# quiet league: the draft polled `transfer` for its own movements and was
# blind for a whole season without a single error.


def test_each_board_builder_pins_its_own_type():
    assert "type=text" in league_board_url(TEST_LEAGUE_ID)
    assert "type=transfer" in league_board_url(TEST_LEAGUE_ID, "transfer")
    assert "type=transfer" in clausulazos_url(TEST_LEAGUE_ID)
    # An admin transfer is not a clause and never shows up in `transfer`.
    assert "type=adminTransfer" in admin_transfers_url(TEST_LEAGUE_ID)
    assert "type=transfer&" not in admin_transfers_url(TEST_LEAGUE_ID)
