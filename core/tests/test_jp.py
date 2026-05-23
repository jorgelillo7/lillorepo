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


def _batch(start_ts: int) -> list[dict]:
    """A 5-player sample with `updated_at` values spread over ~120 seconds —
    matches JP's real shape where each player gets its own timestamp
    inside the batch window."""
    return [_player(i, f"P{i}", updated_at=start_ts + (i * 30)) for i in range(1, 6)]


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


def test_fetch_all_players_uses_cache_when_fingerprint_unchanged():
    """Second call hits a `limit=5` peek but reuses the cached payload.

    The probe and the cached fingerprint both compute `max(updated_at)`
    across the same top-N sample, so unchanged data → identical maxes
    → cache hit.
    """
    batch = _batch(start_ts=1779000000)
    with requests_mock.Mocker() as m:
        m.get(JP_URL, json={"players": batch})
        first = fetch_all_players(TOKEN)
        second = fetch_all_players(TOKEN)
        assert first == second
        limits = [req.qs.get("limit", [""])[0] for req in m.request_history]
        # 1 cold full + 1 warm probe = 2 calls. The probe sends limit=5
        # (sample size); the cold full sends the default 600.
        assert limits == ["600", "5"]


def test_fetch_all_players_invalidates_when_any_top_player_refreshes():
    """A new max within the probe sample triggers re-fetch."""
    stale = _batch(start_ts=1779000000)
    # Same five players, but one of them got a newer timestamp → max moves up.
    fresh = _batch(start_ts=1779000000)
    fresh[2]["predict"][0]["updated_at"] = 1779999999  # third player refreshed

    with requests_mock.Mocker() as m:
        m.get(JP_URL, json={"players": stale})
        fetch_all_players(TOKEN)
        m.get(JP_URL, json={"players": fresh})
        second = fetch_all_players(TOKEN)
        # Cache invalidated because probe's max (1779999999) differs from
        # the cached max (1779000000 + 4*30 = 1779000120).
        assert second == fresh
        limits = [req.qs.get("limit", [""])[0] for req in m.request_history]
        # cold full + probe (sees newer max) + full re-fetch = 3 calls.
        assert limits == ["600", "5", "600"]


def test_fetch_all_players_probe_resilient_to_player_without_timestamp():
    """Cache stays valid when the probe sample includes a player without
    `predict[type=2]` — the max ignores `None`s and uses the rest."""
    batch_with_gap = _batch(start_ts=1779000000)
    batch_with_gap[0]["predict"] = []  # first player has no prediction

    with requests_mock.Mocker() as m:
        m.get(JP_URL, json={"players": batch_with_gap})
        first = fetch_all_players(TOKEN)
        second = fetch_all_players(TOKEN)
        assert first == second
        # Still serves from cache on the second call.
        limits = [req.qs.get("limit", [""])[0] for req in m.request_history]
        assert limits == ["600", "5"]


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
