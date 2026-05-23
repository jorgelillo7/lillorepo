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


# --- /budget/recommendations ---


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


def test_compute_dynamic_margin_scales_with_cash():
    from packages.biwenger_tools.api.logic import recommendations as recs

    # cash ≤ 0 → minimum
    assert recs.compute_dynamic_margin(0) == 2_000_000
    assert recs.compute_dynamic_margin(-100) == 2_000_000
    # 40% of cash, rounded to nearest 500k, clamped [2M, 10M]
    assert recs.compute_dynamic_margin(5_000_000) == 2_000_000  # 0.4*5M=2M (floor)
    assert recs.compute_dynamic_margin(12_972_212) == 5_000_000  # ~5.19M → round 5.0
    assert recs.compute_dynamic_margin(20_000_000) == 8_000_000
    assert recs.compute_dynamic_margin(30_000_000) == 10_000_000  # cap
    assert recs.compute_dynamic_margin(100_000_000) == 10_000_000  # cap


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
        _row(3, "Expensive", pos=2, clause=100_000_000),  # excluded: > target
        _row(4, "Cheap", pos=2, clause=20_000_000),  # included
        _row(5, "NoSF", pos=2, sf=0, clause=15_000_000),  # excluded: SF 0
    ]
    out = recs._filter_affordable(rows, my_ids, target=50_000_000)
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


def test_format_telegram_text_includes_multi_badge_and_exact_euros():
    from packages.biwenger_tools.api.logic import recommendations as recs

    payload = {
        "budget": {
            "cash": 12_972_212,
            "max_bid": 36_334_712,
            "margin": 5_000_000,
            "margin_source": "auto",
            "target": 17_972_212,
        },
        "recommendations": {
            "GK": [],
            "DEF": [
                {
                    "bw_id": 1,
                    "name": "Vivian",
                    "owner": "Ana",
                    "clause": 12_345_678,
                    "sf": 410,
                    "multi": ["MED"],
                }
            ],
            "MID": [],
            "FWD": [],
        },
    }
    text = recs._format_telegram_text(payload)
    # Exact euros in Spanish format (dots as thousands separators).
    assert "12.972.212 €" in text
    assert "17.972.212 €" in text
    assert "36.334.712 €" in text
    assert "auto" in text  # margin_source label
    assert "Vivian (Ana)" in text
    assert "12.345.678 €" in text
    assert "SF 410" in text
    assert "multi: MED" in text


def test_format_telegram_text_marks_manual_margin():
    from packages.biwenger_tools.api.logic import recommendations as recs

    payload = {
        "budget": {
            "cash": 10_000_000,
            "max_bid": 30_000_000,
            "margin": 8_000_000,
            "margin_source": "manual",
            "target": 18_000_000,
        },
        "recommendations": {"GK": [], "DEF": [], "MID": [], "FWD": []},
    }
    text = recs._format_telegram_text(payload)
    assert "fijo" in text


def test_format_telegram_text_dashes_when_max_bid_missing():
    from packages.biwenger_tools.api.logic import recommendations as recs

    payload = {
        "budget": {
            "cash": 12_972_212,
            "max_bid": 0,  # max_bid couldn't be computed (no squad data)
            "margin": 5_000_000,
            "margin_source": "auto",
            "target": 17_972_212,
        },
        "recommendations": {"GK": [], "DEF": [], "MID": [], "FWD": []},
    }
    text = recs._format_telegram_text(payload)
    assert "Puja máx. Biwenger: —" in text


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


def _digest_env(*, auto_bid_result=None, auto_bid_raises=None):
    """Helper: wire `run_daily`'s collaborators so only auto_bid varies.

    Returns the entered ExitStack — the caller must close it. Designed
    for the two tests below that pin the chaining behaviour.
    """
    from contextlib import ExitStack

    stack = ExitStack()
    mock_cfg = stack.enter_context(patch(_patches("config")))
    stack.enter_context(patch(_patches("check_api_health")))
    stack.enter_context(patch(_patches("fetch_all_players"), return_value=[]))
    stack.enter_context(
        patch(_patches("build_jp_index"), return_value={"by_name": {}, "by_slug": {}})
    )
    mock_client = stack.enter_context(patch(_patches("BiwengerClient")))
    mock_send = stack.enter_context(patch(_patches("_send_image")))
    # `build_table_image` runs synchronously before `_send_image` — patching
    # the renderer avoids matplotlib choking on the empty-row stub data.
    stack.enter_context(patch(_patches("build_table_image"), return_value=b""))
    if auto_bid_raises is not None:
        mock_auto_bid = stack.enter_context(
            patch(_patches("auto_bid.run_auto_bid"), side_effect=auto_bid_raises)
        )
    else:
        mock_auto_bid = stack.enter_context(
            patch(_patches("auto_bid.run_auto_bid"), return_value=auto_bid_result or {})
        )

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
    mock_cfg.TELEGRAM_BOT_TOKEN = "tok"
    mock_cfg.TELEGRAM_CHAT_ID = "chat"
    mock_client.return_value.user_id = 1
    mock_client.return_value.get_all_players_data_map.return_value = {}
    mock_client.return_value.get_manager_squad.return_value = []
    mock_client.return_value.get_market_players.return_value = []
    return stack, mock_send, mock_auto_bid


def test_run_daily_chains_auto_bid_after_sending_images():
    """`run_daily` must call `auto_bid.run_auto_bid()` exactly once, after
    both PNGs have been sent — that's what gives the chat a clean
    squad → market → bids ordering."""
    stack, mock_send, mock_auto_bid = _digest_env(
        auto_bid_result={"bid_count": 2, "skipped_count": 3, "total_bid_eur": 4_000_000}
    )
    try:
        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    finally:
        stack.close()

    mock_auto_bid.assert_called_once()
    # 2 image sends happened first (my team + market).
    assert mock_send.call_count == 2
    assert result["sent"] == 2
    assert result["auto_bid"]["bid_count"] == 2


def test_run_daily_swallows_auto_bid_failure_and_still_returns_digest_summary():
    """A broken auto-bid run must not lose the digest we already sent. The
    summary surfaces the error, but the route stays 200 OK."""
    stack, mock_send, mock_auto_bid = _digest_env(
        auto_bid_raises=RuntimeError("biwenger 503")
    )
    try:
        from packages.biwenger_tools.api.logic import digests

        result = digests.run_daily()
    finally:
        stack.close()

    mock_auto_bid.assert_called_once()
    assert mock_send.call_count == 2
    assert result["sent"] == 2
    assert "error" in result["auto_bid"]
    assert "biwenger 503" in result["auto_bid"]["error"]
