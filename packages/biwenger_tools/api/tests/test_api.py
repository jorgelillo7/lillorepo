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


# --- /teams, /teams/mine, /market, /lineups/auto-pick ---


def test_teams_calls_run_all_teams(client):
    fake = {"sent": 5, "teams": 4, "market": 6}
    with patch(
        "packages.biwenger_tools.api.app.actions.run_all_teams",
        return_value=fake,
    ) as mock_run:
        resp = client.get("/teams")
    mock_run.assert_called_once()
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["teams"] == 4


def test_teams_mine_calls_run_my_team(client):
    with patch(
        "packages.biwenger_tools.api.app.actions.run_my_team",
        return_value={"sent": 1, "size": 12},
    ) as mock_run:
        resp = client.get("/teams/mine")
    mock_run.assert_called_once()
    assert resp.status_code == 200
    assert resp.get_json()["size"] == 12


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
    mock_run.assert_called_once()
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["applied"] is True
    assert body["formation"] == "4-3-3"


def test_lineups_auto_pick_rejects_get(client):
    resp = client.get("/lineups/auto-pick")
    assert resp.status_code == 405


def test_action_endpoint_returns_500_on_exception(client):
    with patch(
        "packages.biwenger_tools.api.app.actions.run_all_teams",
        side_effect=RuntimeError("biwenger 503"),
    ):
        resp = client.get("/teams")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["status"] == "error"
    assert "biwenger 503" in body["error"]


# --- /budget/recommendations ---


def test_budget_recommendations_calls_run_with_default_top(client):
    fake = {
        "sent": 1,
        "budget": {"cash": 7_000_000, "max_bid": 35_000_000},
        "recommendations": {"GK": [], "DEF": [], "MID": [], "FWD": []},
    }
    with patch(
        "packages.biwenger_tools.api.app.recommendations.run_recommendations",
        return_value=fake,
    ) as mock_run:
        resp = client.get("/budget/recommendations")
    mock_run.assert_called_once_with(top=3)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["budget"]["cash"] == 7_000_000


def test_budget_recommendations_respects_top_query_param(client):
    fake = {"sent": 1, "budget": {"cash": 0, "max_bid": 0}, "recommendations": {}}
    with patch(
        "packages.biwenger_tools.api.app.recommendations.run_recommendations",
        return_value=fake,
    ) as mock_run:
        client.get("/budget/recommendations?top=5")
    mock_run.assert_called_once_with(top=5)


def test_budget_recommendations_clamps_top_param(client):
    fake = {"sent": 1, "budget": {"cash": 0, "max_bid": 0}, "recommendations": {}}
    with patch(
        "packages.biwenger_tools.api.app.recommendations.run_recommendations",
        return_value=fake,
    ) as mock_run:
        client.get("/budget/recommendations?top=99")
        client.get("/budget/recommendations?top=0")
        client.get("/budget/recommendations?top=garbage")
    # 99 → 10, 0 → 1, garbage → default 3
    calls = [c.kwargs["top"] for c in mock_run.call_args_list]
    assert calls == [10, 1, 3]


# --- recommendations unit tests (filtering + grouping) ---


def _row(bw_id, name, pos, alt=None, sf=300, clause=10_000_000, clausulable=True):
    return {
        "bw_id": bw_id,
        "name": name,
        "position_id": pos,
        "alt_positions": alt or [],
        "owner": "Pepe",
        "jp_player": {"predict": [{"type": 2, "rate": sf}]},
        "Clausulable": "Sí" if clausulable else "No (5d)",
        "Cláusula": f"{clause / 1_000_000:.1f}M",
        "clause_value": clause,
        "clausulable_now": clausulable,
    }


def test_filter_affordable_excludes_my_players_and_locked_and_too_expensive():
    from packages.biwenger_tools.api.logic import recommendations as recs

    my_ids = {1}
    rows = [
        _row(1, "Mine", pos=2),  # excluded: mine
        _row(2, "Locked", pos=2, clausulable=False),  # excluded: locked
        _row(3, "Expensive", pos=2, clause=100_000_000),  # excluded: > max_bid
        _row(4, "Cheap", pos=2, clause=20_000_000),  # included
        _row(5, "NoSF", pos=2, sf=0, clause=15_000_000),  # excluded: SF 0
    ]
    out = recs._filter_affordable(rows, my_ids, max_bid=50_000_000)
    assert [r["bw_id"] for r in out] == [4]


def test_top_per_position_groups_by_primary_and_marks_multi():
    from packages.biwenger_tools.api.logic import recommendations as recs

    rows = [
        # 2 defs, top 1 of which is also MID-eligible
        _row(10, "Def1", pos=2, alt=[3], sf=500, clause=10_000_000),
        _row(11, "Def2", pos=2, sf=400, clause=12_000_000),
        # 1 GK
        _row(20, "Gk1", pos=1, sf=350, clause=8_000_000),
    ]
    out = recs._pick_top_per_position(rows, top=3)
    assert len(out["GK"]) == 1
    assert len(out["DEF"]) == 2
    assert len(out["MID"]) == 0  # multi-position does NOT duplicate to MID
    assert out["DEF"][0]["multi"] == ["MED"]
    assert out["DEF"][1]["multi"] == []


def test_top_per_position_caps_at_top_n():
    from packages.biwenger_tools.api.logic import recommendations as recs

    rows = [_row(i, f"X{i}", pos=4, sf=400 - i, clause=10_000_000) for i in range(10)]
    out = recs._pick_top_per_position(rows, top=3)
    assert len(out["FWD"]) == 3
    # sorted by SF desc
    assert out["FWD"][0]["sf"] > out["FWD"][1]["sf"] > out["FWD"][2]["sf"]


def test_format_telegram_text_includes_multi_badge():
    from packages.biwenger_tools.api.logic import recommendations as recs

    payload = {
        "budget": {"cash": 7_000_000, "max_bid": 35_000_000},
        "recommendations": {
            "GK": [],
            "DEF": [
                {
                    "bw_id": 1,
                    "name": "Vivian",
                    "owner": "Ana",
                    "clause": 12_000_000,
                    "sf": 410,
                    "multi": ["MED"],
                }
            ],
            "MID": [],
            "FWD": [],
        },
    }
    text = recs._format_telegram_text(payload)
    assert "Cash: 7M" in text
    assert "Max bid: 35M" in text
    assert "Vivian (Ana)" in text
    assert "12M" in text
    assert "SF 410" in text
    assert "multi: MED" in text


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
