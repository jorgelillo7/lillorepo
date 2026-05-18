"""Tests for the Biwenger API endpoints."""

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


# --- /digests/daily ---


def test_digests_daily_calls_run_daily_and_returns_summary(client):
    fake = {"sent": 2, "my_team": 12, "market": 8}
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


# --- digests.run_daily unit tests ---


def _make_jp_player(name, sf=200, status="ok"):
    return {
        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "status": status,
        "predict": [{"type": 2, "rate": sf}],
        "nextMatch": {"status": "ok", "isLocal": True, "playerInLineup": True},
    }


def _patches(target):
    return f"packages.biwenger_tools.api.logic.digests.{target}"


def test_run_daily_skips_send_when_telegram_creds_missing(client):
    with patch(_patches("config")) as mock_cfg, patch(
        _patches("check_api_health")
    ), patch(_patches("fetch_all_players"), return_value=[]), patch(
        _patches("build_jp_index"), return_value={"by_name": {}, "by_slug": {}}
    ), patch(
        _patches("BiwengerClient")
    ) as mock_client, patch(
        _patches("_send_image")
    ) as mock_send:
        mock_cfg.JP_AUTH_TOKEN = "tok"
        mock_cfg.JP_COMPETITION = 1
        mock_cfg.JP_SCORE_TYPE = 2
        mock_cfg.BIWENGER_EMAIL = "u"
        mock_cfg.BIWENGER_PASSWORD = "p"
        mock_cfg.LOGIN_URL = mock_cfg.ACCOUNT_URL = "x"
        mock_cfg.LEAGUE_ID = "1"
        mock_cfg.ALL_PLAYERS_DATA_URL = "x"
        mock_cfg.USER_SQUAD_URL = "x/{manager_id}"
        mock_cfg.MARKET_URL = "x"
        mock_cfg.TELEGRAM_BOT_TOKEN = ""
        mock_cfg.TELEGRAM_CHAT_ID = ""
        mock_client.return_value.user_id = 1
        mock_client.return_value.get_all_players_data_map.return_value = {}

        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    assert result["sent"] == 0
    assert result["reason"] == "telegram_credentials_missing"
    mock_send.assert_not_called()
