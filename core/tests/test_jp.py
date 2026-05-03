import pytest
import requests_mock

from core.sdk.jp import (
    JP_URL,
    check_api_health,
    fetch_all_players,
    get_predict_rate,
)

TOKEN = "abc"


def test_fetch_all_players_returns_list():
    with requests_mock.Mocker() as m:
        m.get(JP_URL, json={"players": [{"id": 1, "name": "X"}]})
        players = fetch_all_players(TOKEN)
        assert players == [{"id": 1, "name": "X"}]
        # Sanity-check the params we send
        sent = m.last_request.qs
        assert sent["auth"] == [TOKEN]
        assert sent["showpredict"] == ["true"]
        assert sent["limit"] == ["600"]


def test_get_predict_rate_returns_value():
    player = {
        "predict": [
            {"type": 1, "rate": 100},
            {"type": 2, "rate": 200},
            {"type": 16, "rate": 150},
        ]
    }
    assert get_predict_rate(player, 2) == 200
    assert get_predict_rate(player, 1) == 100


def test_get_predict_rate_returns_none_when_missing():
    assert get_predict_rate({"predict": []}, 2) is None
    assert get_predict_rate({}, 2) is None
    assert get_predict_rate({"predict": [{"type": 1, "rate": 100}]}, 2) is None


def test_check_api_health_raises_on_empty_players():
    with requests_mock.Mocker() as m:
        m.get(JP_URL, json={"players": []})
        with pytest.raises(RuntimeError, match="token posiblemente rotado"):
            check_api_health(TOKEN)


def test_check_api_health_raises_on_http_error():
    with requests_mock.Mocker() as m:
        m.get(JP_URL, status_code=403, json={})
        with pytest.raises(RuntimeError):
            check_api_health(TOKEN)


def test_check_api_health_passes_on_success():
    with requests_mock.Mocker() as m:
        m.get(JP_URL, json={"players": [{"id": 1}]})
        check_api_health(TOKEN)  # no raise
