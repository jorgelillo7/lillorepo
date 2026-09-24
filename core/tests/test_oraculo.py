"""Unit tests for `core/sdk/oraculo.py`.

Every payload comes from `tests/data/`; nothing here touches the network. The
two fixtures are hand-built in the shape the real sources serve — a JSON body
for the API, and an HTML page carrying the RSC flight payload the page route
hides its data in.
"""

import os

import pytest
import requests
import requests_mock

from core.sdk import oraculo


@pytest.fixture(autouse=True)
def reset_cache():
    oraculo._CACHE.clear()
    yield
    oraculo._CACHE.clear()


def _data(name):
    path = os.path.join(os.path.dirname(__file__), "data", name)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def picks_body():
    import json

    return json.loads(_data("oraculo_picks.json"))


@pytest.fixture
def predictions_html():
    return _data("oraculo_predictions.html")


# --- fetch_picks -----------------------------------------------------------


def test_picks_returns_the_lists_and_the_matchday(picks_body):
    with requests_mock.Mocker() as m:
        m.get(oraculo.picks_url(), json=picks_body)
        result = oraculo.fetch_picks()
    assert result["matchday"] == 7
    assert result["generated_at"] == "2026-09-16T21:00:00+00:00"
    assert sorted(result["picks"]) == [
        "asistentes",
        "capitanes",
        "centrocampistas",
        "chollos",
        "defensas",
        "delanteros",
        "goleadores",
        "porteros",
    ]


def test_the_scoring_system_is_verified_not_assumed(picks_body):
    """The single check that matters. The page routes serve LaLiga Fantasy
    where this serves Biwenger, and the same player reads 7.38 on one and 3.60
    on the other — so a silently swapped default would halve every projection
    while looking healthy."""
    picks_body["data"]["sistema"] = "la-liga-fantasy"
    with requests_mock.Mocker() as m:
        m.get(oraculo.picks_url(), json=picks_body)
        with pytest.raises(oraculo.OraculoError, match="sistema"):
            oraculo.fetch_picks()


def test_lists_a_player_belongs_to_are_resolvable(picks_body):
    with requests_mock.Mocker() as m:
        m.get(oraculo.picks_url(), json=picks_body)
        result = oraculo.fetch_picks()
    assert oraculo.lists_for(result, 2) == ["delanteros", "goleadores"]
    assert oraculo.lists_for(result, 1) == ["chollos"]
    assert oraculo.lists_for(result, 999) == []


def test_an_http_failure_raises_rather_than_returning_nothing():
    """A silent empty list would read as 'Oráculo has no opinion on anybody',
    which is indistinguishable from a thin midweek read — and the two call for
    opposite responses."""
    with requests_mock.Mocker() as m:
        m.get(oraculo.picks_url(), status_code=500)
        with pytest.raises(oraculo.OraculoError):
            oraculo.fetch_picks()


def test_a_timeout_raises_too():
    with requests_mock.Mocker() as m:
        m.get(oraculo.picks_url(), exc=requests.exceptions.ConnectTimeout)
        with pytest.raises(oraculo.OraculoError):
            oraculo.fetch_picks()


def test_the_second_call_is_served_from_cache(picks_body):
    with requests_mock.Mocker() as m:
        m.get(oraculo.picks_url(), json=picks_body)
        oraculo.fetch_picks()
        oraculo.fetch_picks()
        assert m.call_count == 1


# --- fetch_predictions -----------------------------------------------------


def test_predictions_are_read_out_of_the_flight_payload(predictions_html):
    """The page ships its data inside `self.__next_f.push([1, "..."])`. This is
    the fragile half of the reader: a framework change breaks this test, loudly,
    rather than the service."""
    with requests_mock.Mocker() as m:
        m.get(oraculo.PREDICTIONS_URL, text=predictions_html)
        rows = oraculo.fetch_predictions()
    assert {r["playerId"] for r in rows} == {10, 11, 12}


def test_an_unparseable_page_raises(predictions_html):
    with requests_mock.Mocker() as m:
        m.get(oraculo.PREDICTIONS_URL, text="<html>no flight payload here</html>")
        with pytest.raises(oraculo.OraculoError):
            oraculo.fetch_predictions()


def test_rows_are_filtered_to_one_matchday(predictions_html):
    """The page carries the matchday in play and the one coming at once. Mixing
    them would score a squad against games already played."""
    with requests_mock.Mocker() as m:
        m.get(oraculo.PREDICTIONS_URL, text=predictions_html)
        rows = oraculo.fetch_predictions()
    kept = oraculo.rows_for_dates(rows, {"2026-09-18", "2026-09-20"})
    assert {r["playerId"] for r in kept} == {10, 12}


def test_matchday_dates_come_from_the_api_fixtures(picks_body):
    with requests_mock.Mocker() as m:
        m.get(oraculo.picks_url(), json=picks_body)
        result = oraculo.fetch_picks()
    assert oraculo.matchday_dates(result) == {"2026-09-18", "2026-09-20"}


def test_a_row_without_a_projection_is_kept_and_marked(predictions_html):
    """Zero is an answer — the site shows `Esperado 0.00` for a player it
    expects not to play. Dropping the row would be indistinguishable from
    Oráculo not carrying him, and those mean different things."""
    with requests_mock.Mocker() as m:
        m.get(oraculo.PREDICTIONS_URL, text=predictions_html)
        rows = oraculo.fetch_predictions()
    no_points = next(r for r in rows if r["playerId"] == 12)
    assert no_points["predictedPoints"] == 0


# --- the client says who it is ---------------------------------------------


def test_the_reader_identifies_itself(picks_body):
    """Never a copy of browser headers. The site keeps the ability to see,
    rate-limit or block this, which is the difference between reading and
    hiding."""
    with requests_mock.Mocker() as m:
        m.get(oraculo.picks_url(), json=picks_body)
        oraculo.fetch_picks()
        agent = m.last_request.headers["User-Agent"]
    assert "lillorepo" in agent
    assert "Mozilla" not in agent


def test_the_cache_expires_after_its_ttl(picks_body, monkeypatch):
    """The model retrains hourly; past the TTL the next read has to reach the
    site again, or a warm instance would serve yesterday's picks forever."""
    now = [1000.0]
    monkeypatch.setattr(oraculo.time, "monotonic", lambda: now[0])
    with requests_mock.Mocker() as m:
        m.get(oraculo.picks_url(), json=picks_body)
        oraculo.fetch_picks()
        now[0] += oraculo.CACHE_TTL_SECONDS - 1
        oraculo.fetch_picks()
        assert m.call_count == 1
        now[0] += 2
        oraculo.fetch_picks()
        assert m.call_count == 2
