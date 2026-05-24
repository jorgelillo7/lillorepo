"""Tests for the Flask route handlers in `api/app.py`.

These pin the wiring (path → logic function, query-param parsing,
exception → 500, allowed HTTP methods). Logic-layer behaviour is
tested in the per-feature test files (`test_recommendations.py`,
`test_digests.py`, `test_auto_bid.py`).
"""

from unittest.mock import patch

import pytest

import packages.biwenger_tools.api.config as cfg
from packages.biwenger_tools.api.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# --- /health ---


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_unknown_path_returns_404(client):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404


# --- /version ---


def test_version_returns_service_metadata(client):
    cfg.GIT_COMMIT = "abc1234"
    cfg.DEPLOY_TIME = "17/05/2026 14:00"
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["service"] == "biwenger-api"
    assert body["commit"] == "abc1234"
    assert body["deploy_time"] == "17/05/2026 14:00"


def test_version_tolerates_missing_metadata(client):
    cfg.GIT_COMMIT = ""
    cfg.DEPLOY_TIME = ""
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["commit"] == "unknown"


# --- /scraper/trigger ---


def test_scraper_trigger_queues_job(client):
    fake = {"queued": True, "execution": "abc-123", "job": "biwenger-scraper-data"}
    with patch(
        "packages.biwenger_tools.api.app.scraper.run_trigger_scraper",
        return_value=fake,
    ) as mock_run:
        resp = client.post("/scraper/trigger")
    mock_run.assert_called_once()
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["queued"] is True
    assert body["execution"] == "abc-123"


def test_scraper_trigger_returns_500_on_exception(client):
    with patch(
        "packages.biwenger_tools.api.app.scraper.run_trigger_scraper",
        side_effect=RuntimeError("perm denied"),
    ):
        resp = client.post("/scraper/trigger")
    assert resp.status_code == 500
    assert "perm denied" in resp.get_json()["error"]


def test_scraper_trigger_rejects_get(client):
    resp = client.get("/scraper/trigger")
    assert resp.status_code == 405


# --- /digests/daily ---


def test_digests_daily_calls_run_daily_and_returns_summary(client):
    fake = {
        "sent": 2,
        "my_team": 12,
        "market": 8,
        "auto_bid": {"bid_count": 1, "skipped_count": 2, "total_bid_eur": 5_000_000},
    }
    with patch(
        "packages.biwenger_tools.api.app.digests.run_daily",
        return_value=fake,
    ) as mock_run:
        resp = client.post("/digests/daily")
    mock_run.assert_called_once()
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["sent"] == 2
    assert body["my_team"] == 12
    assert body["market"] == 8
    assert body["auto_bid"]["bid_count"] == 1


def test_digests_daily_returns_500_on_exception(client):
    with patch(
        "packages.biwenger_tools.api.app.digests.run_daily",
        side_effect=RuntimeError("biwenger 503"),
    ):
        resp = client.post("/digests/daily")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["status"] == "error"
    assert "biwenger 503" in body["error"]


def test_digests_daily_rejects_get(client):
    resp = client.get("/digests/daily")
    assert resp.status_code == 405  # method not allowed


# --- /market/auto-bid ---


def test_market_auto_bid_calls_run_auto_bid(client):
    fake = {
        "sent": 1,
        "day": "2026-05-23",
        "candidates": 7,
        "bid_count": 2,
        "skipped_count": 5,
        "total_bid_eur": 12_000_000,
        "remaining_cash_eur": 1_000_000,
        "bids": [],
    }
    with patch(
        "packages.biwenger_tools.api.app.auto_bid.run_auto_bid",
        return_value=fake,
    ) as mock_run:
        resp = client.post("/market/auto-bid")
    mock_run.assert_called_once()
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["bid_count"] == 2
    assert body["total_bid_eur"] == 12_000_000


def test_market_auto_bid_returns_500_on_exception(client):
    with patch(
        "packages.biwenger_tools.api.app.auto_bid.run_auto_bid",
        side_effect=RuntimeError("biwenger 503"),
    ):
        resp = client.post("/market/auto-bid")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["status"] == "error"
    assert "biwenger 503" in body["error"]


def test_market_auto_bid_rejects_get(client):
    resp = client.get("/market/auto-bid")
    assert resp.status_code == 405


# --- /teams, /managers, /market, /lineups/auto-pick ---


def test_teams_without_manager_calls_run_teams_with_none(client):
    """No `manager` query → run_teams(None) (all-managers + market)."""
    fake = {"sent": 5, "teams": 4, "market": 6}
    with patch(
        "packages.biwenger_tools.api.app.actions.run_teams",
        return_value=fake,
    ) as mock_run:
        resp = client.get("/teams")
    mock_run.assert_called_once_with(None)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["teams"] == 4


def test_teams_with_manager_id_filters(client):
    """`?manager=42` → run_teams(42) (single-squad image, no market)."""
    with patch(
        "packages.biwenger_tools.api.app.actions.run_teams",
        return_value={"sent": 1, "manager": "Jorge", "size": 12},
    ) as mock_run:
        resp = client.get("/teams?manager=42")
    mock_run.assert_called_once_with(42)
    assert resp.status_code == 200
    assert resp.get_json()["size"] == 12


def test_teams_with_manager_all_is_alias_for_no_filter(client):
    """`?manager=all` is treated the same as omitting the param."""
    with patch(
        "packages.biwenger_tools.api.app.actions.run_teams",
        return_value={"sent": 5, "teams": 4, "market": 6},
    ) as mock_run:
        resp = client.get("/teams?manager=all")
    mock_run.assert_called_once_with(None)
    assert resp.status_code == 200


def test_teams_with_invalid_manager_returns_400(client):
    """A non-integer `manager` param is rejected upfront."""
    resp = client.get("/teams?manager=abc")
    assert resp.status_code == 400
    assert "manager must be an integer" in resp.get_json()["error"]


def test_managers_endpoint(client):
    """The picker endpoint exposes the manager list to the bot."""
    fake = {
        "managers": [
            {"id": 1, "name": "Jorge", "is_me": True},
            {"id": 2, "name": "Pepe", "is_me": False},
        ]
    }
    with patch(
        "packages.biwenger_tools.api.app.actions.list_managers",
        return_value=fake,
    ) as mock_run:
        resp = client.get("/managers")
    mock_run.assert_called_once()
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["managers"][0]["is_me"] is True


def test_market_calls_run_market(client):
    with patch(
        "packages.biwenger_tools.api.app.actions.run_market",
        return_value={"sent": 1, "size": 7},
    ) as mock_run:
        resp = client.get("/market")
    mock_run.assert_called_once()
    assert resp.status_code == 200
    assert resp.get_json()["size"] == 7


def test_lineups_auto_pick_calls_run_auto_pick(client):
    fake = {"sent": 1, "applied": True, "formation": "4-3-3", "total_sf": 4200}
    with patch(
        "packages.biwenger_tools.api.app.actions.run_auto_pick_lineup",
        return_value=fake,
    ) as mock_run:
        resp = client.post("/lineups/auto-pick")
    mock_run.assert_called_once_with(dry_run=False)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["applied"] is True
    assert body["formation"] == "4-3-3"


def test_lineups_auto_pick_with_dry_run_flag(client):
    """`?dry_run=1` flips `run_auto_pick_lineup(dry_run=True)`."""
    fake = {
        "sent": 1,
        "applied": False,
        "dry_run": True,
        "formation": "4-3-3",
        "total_sf": 4200,
    }
    with patch(
        "packages.biwenger_tools.api.app.actions.run_auto_pick_lineup",
        return_value=fake,
    ) as mock_run:
        resp = client.post("/lineups/auto-pick?dry_run=1")
    mock_run.assert_called_once_with(dry_run=True)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["applied"] is False
    assert body["dry_run"] is True


def test_lineups_auto_pick_rejects_get(client):
    resp = client.get("/lineups/auto-pick")
    assert resp.status_code == 405


def test_action_endpoint_returns_500_on_exception(client):
    with patch(
        "packages.biwenger_tools.api.app.actions.run_teams",
        side_effect=RuntimeError("biwenger 503"),
    ):
        resp = client.get("/teams")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["status"] == "error"
    assert "biwenger 503" in body["error"]


# --- /budget/recommendations (route only, logic in test_recommendations.py) ---


def test_budget_recommendations_defaults_to_dynamic_margin(client):
    fake = {
        "sent": 1,
        "budget": {
            "cash": 7_000_000,
            "max_bid": 35_000_000,
            "margin": 2_500_000,
            "margin_source": "auto",
            "target": 9_500_000,
        },
        "recommendations": {"GK": [], "DEF": [], "MID": [], "FWD": []},
    }
    with patch(
        "packages.biwenger_tools.api.app.recommendations.run_recommendations",
        return_value=fake,
    ) as mock_run:
        resp = client.get("/budget/recommendations")
    # No `margin` query param → dynamic (None passed through).
    mock_run.assert_called_once_with(top=3, margin=None)
    assert resp.status_code == 200


def test_budget_recommendations_respects_explicit_top_and_margin(client):
    fake = {
        "sent": 1,
        "budget": {
            "cash": 0,
            "max_bid": 0,
            "margin": 10_000_000,
            "margin_source": "manual",
            "target": 10_000_000,
        },
        "recommendations": {},
    }
    with patch(
        "packages.biwenger_tools.api.app.recommendations.run_recommendations",
        return_value=fake,
    ) as mock_run:
        client.get("/budget/recommendations?top=5&margin=10000000")
    mock_run.assert_called_once_with(top=5, margin=10_000_000)


def test_budget_recommendations_clamps_query_params(client):
    fake = {
        "sent": 1,
        "budget": {
            "cash": 0,
            "max_bid": 0,
            "margin": 0,
            "margin_source": "manual",
            "target": 0,
        },
        "recommendations": {},
    }
    with patch(
        "packages.biwenger_tools.api.app.recommendations.run_recommendations",
        return_value=fake,
    ) as mock_run:
        client.get("/budget/recommendations?top=99&margin=99999999999")
        client.get("/budget/recommendations?top=0&margin=-1")
        client.get("/budget/recommendations?top=garbage&margin=garbage")
    calls = mock_run.call_args_list
    # top: 99 → 10, 0 → 1, garbage → 3 (default)
    assert [c.kwargs["top"] for c in calls] == [10, 1, 3]
    # margin: 99999999999 → 50M, -1 → 0, garbage → None (fall back to dynamic)
    assert [c.kwargs["margin"] for c in calls] == [50_000_000, 0, None]
