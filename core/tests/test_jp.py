import pytest
import requests
import requests_mock

from core.sdk import jp
from core.sdk.jp import (
    JP_URL,
    check_api_health,
    fetch_all_players,
    get_predict_rate,
)

TOKEN = "abc"


@pytest.fixture(autouse=True)
def reset_cache():
    """Wipe the in-process JP cache between tests so they stay isolated."""
    jp._CACHE.clear()
    yield
    jp._CACHE.clear()


def _player(pid: int, name: str, updated_at: int = 1779000000) -> dict:
    return {
        "id": pid,
        "name": name,
        "predict": [{"type": 2, "rate": 100 + pid, "updated_at": updated_at}],
    }


def test_fetch_all_players_returns_list():
    with requests_mock.Mocker() as m:
        m.get(JP_URL, json={"players": [_player(1, "X")]})
        players = fetch_all_players(TOKEN)
        assert players == [_player(1, "X")]
        # Sanity-check the params on the last (full) request
        sent = m.last_request.qs
        assert sent["auth"] == [TOKEN]
        assert sent["showpredict"] == ["true"]
        assert sent["limit"] == ["600"]


def test_fetch_all_players_uses_cache_when_updated_at_unchanged():
    """Second call hits a `limit=1` peek but reuses the cached payload."""
    payload = {"players": [_player(1, "X", updated_at=1779000000)]}
    with requests_mock.Mocker() as m:
        m.get(JP_URL, json=payload)
        first = fetch_all_players(TOKEN)
        second = fetch_all_players(TOKEN)
        assert first == second
        # Requests in order: full (no peek on cold cache), peek, …
        # Cold-cache path skips the peek (no cached_players); first call
        # is one full request. The second call peeks and finds the cache
        # still valid → no full re-fetch.
        limits = [req.qs.get("limit", [""])[0] for req in m.request_history]
        # 1 cold full + 1 warm peek = 2 calls total, limits "600" and "1".
        assert limits == ["600", "1"]


def test_fetch_all_players_invalidates_when_updated_at_changes():
    """If the peek shows a newer `updated_at`, we re-fetch in full."""
    stale_payload = {"players": [_player(1, "X", updated_at=1779000000)]}
    fresh_payload = {"players": [_player(1, "X", updated_at=1779999999)]}
    with requests_mock.Mocker() as m:
        m.get(JP_URL, json=stale_payload)
        first = fetch_all_players(TOKEN)
        # JP refreshes: peek + full both return the newer timestamp.
        m.get(JP_URL, json=fresh_payload)
        second = fetch_all_players(TOKEN)
        assert first == [_player(1, "X", updated_at=1779000000)]
        assert second == [_player(1, "X", updated_at=1779999999)]
        limits = [req.qs.get("limit", [""])[0] for req in m.request_history]
        # cold full + peek (sees fresh) + full re-fetch = 3 calls.
        assert limits == ["600", "1", "600"]


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


def test_check_api_health_wraps_connection_error():
    """Network/DNS failures must surface as RuntimeError so the orchestrator's
    top-level except catches a single, well-known type instead of letting
    requests' exception hierarchy leak."""
    with requests_mock.Mocker() as m:
        m.get(JP_URL, exc=requests.exceptions.ConnectionError("DNS down"))
        with pytest.raises(RuntimeError, match="JP API unreachable"):
            check_api_health(TOKEN)
