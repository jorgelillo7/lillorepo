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


# --- /league/compare ---


def test_league_compare_calls_the_action(client):
    with patch(
        "packages.biwenger_tools.api.app.actions.run_league_compare",
        return_value={"sent": 1, "managers": 7},
    ) as mock_run:
        resp = client.post("/league/compare")
    mock_run.assert_called_once()
    assert resp.status_code == 200
    assert resp.get_json()["managers"] == 7


def test_league_compare_rejects_get(client):
    assert client.get("/league/compare").status_code == 405


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


# --- /emergency/clausulazo/preview -----------------------------------------


def test_force_position_outside_the_range_is_a_400_not_a_crash(client):
    """`_reason_force_position` looks up `_POSITION_LABELS_ES[position_id]`
    for whatever `force_position` carries; anything outside the outfield
    range (2-4) — garbage, negative, or the goalkeeper line — must be
    rejected here instead of reaching that lookup."""
    with patch(
        "packages.biwenger_tools.api.app.emergency.preview_clausulazo"
    ) as mock_preview:
        for raw in ("9", "-1", "garbage", "1"):
            resp = client.post(f"/emergency/clausulazo/preview?force_position={raw}")
            assert resp.status_code == 400, raw
            assert "force_position" in resp.get_json()["error"]
    mock_preview.assert_not_called()


# --- /offers/inbox and /offers/decide -------------------------------------


def test_offers_inbox_calls_run_offers_inbox_with_notify_empty(client):
    """On-demand `/offers/inbox` must pass `notify_empty=True` so an
    empty inbox lands a "📭 Sin ofertas" reply in the chat. The digest's
    own call (in `digests.py`) keeps the default silent mode."""
    fake = {"sent": 2, "offers": 2}
    with patch(
        "packages.biwenger_tools.api.app.offers.run_offers_inbox",
        return_value=fake,
    ) as mock_run:
        resp = client.post("/offers/inbox")
    mock_run.assert_called_once_with(notify_empty=True)
    assert resp.status_code == 200
    assert resp.get_json()["sent"] == 2


def test_offers_inbox_rejects_get(client):
    resp = client.get("/offers/inbox")
    assert resp.status_code == 405


def test_offers_decide_accepts(client):
    fake = {
        "sent": 1,
        "offer_id": 42,
        "decision": "accepted",
        "final_status": "processed",
    }
    with patch(
        "packages.biwenger_tools.api.app.offers.run_offer_decision",
        return_value=fake,
    ) as mock_run:
        resp = client.post("/offers/decide?offer_id=42&decision=accepted")
    mock_run.assert_called_once_with(offer_id=42, decision="accepted")
    assert resp.status_code == 200
    assert resp.get_json()["final_status"] == "processed"


def test_offers_decide_rejects_missing_offer_id(client):
    resp = client.post("/offers/decide?decision=accepted")
    assert resp.status_code == 400
    assert "offer_id" in resp.get_json()["error"]


def test_offers_decide_rejects_non_int_offer_id(client):
    resp = client.post("/offers/decide?offer_id=abc&decision=accepted")
    assert resp.status_code == 400


def test_offers_decide_rejects_invalid_decision(client):
    resp = client.post("/offers/decide?offer_id=1&decision=maybe")
    assert resp.status_code == 400
    assert "decision" in resp.get_json()["error"]


def test_offers_decide_rejects_get(client):
    resp = client.get("/offers/decide?offer_id=1&decision=accepted")
    assert resp.status_code == 405


# --- /draft/* --------------------------------------------------------------
# These pin the wiring only — body parsing, method, status codes, and the
# 5xx fallback shape. `draft_service`'s own behaviour is covered in
# test_draft_service.py.


def test_draft_register_calls_service(client):
    fake = {"ok": True, "manager_id": 1, "manager_name": "Ruben", "message": "hola"}
    with patch(
        "packages.biwenger_tools.api.app.draft_service.register_manager",
        return_value=fake,
    ) as mock_run:
        resp = client.post(
            "/draft/register", json={"telegram_user_id": "1", "name": "Ruben"}
        )
    mock_run.assert_called_once_with("1", "Ruben", None)
    assert resp.status_code == 200
    assert resp.get_json() == fake


def test_draft_register_accepts_manager_id_from_the_soy_picker(client):
    fake = {"ok": True, "manager_id": 7, "manager_name": "Manu", "message": "hola"}
    with patch(
        "packages.biwenger_tools.api.app.draft_service.register_manager",
        return_value=fake,
    ) as mock_run:
        resp = client.post(
            "/draft/register", json={"telegram_user_id": "1", "manager_id": 7}
        )
    mock_run.assert_called_once_with("1", "", 7)
    assert resp.status_code == 200


def test_draft_managers_lists_the_picker_options(client):
    fake = {
        "managers": [{"manager_id": 1, "name": "Ruben", "claimed_by": ""}],
        "message": "x",
    }
    with patch(
        "packages.biwenger_tools.api.app.draft_service.list_draft_managers",
        return_value=fake,
    ):
        resp = client.get("/draft/managers")
    assert resp.status_code == 200
    assert resp.get_json() == fake


def test_draft_register_rejects_missing_fields(client):
    resp = client.post("/draft/register", json={"telegram_user_id": "1"})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_draft_register_returns_500_on_exception(client):
    with patch(
        "packages.biwenger_tools.api.app.draft_service.register_manager",
        side_effect=RuntimeError("firestore down"),
    ):
        resp = client.post(
            "/draft/register", json={"telegram_user_id": "1", "name": "Ruben"}
        )
    assert resp.status_code == 500
    assert "firestore down" in resp.get_json()["message"]


def test_draft_register_rejects_get(client):
    resp = client.get("/draft/register")
    assert resp.status_code == 405


def test_draft_state_calls_service(client):
    fake = {
        "completed": False,
        "pick_number": 1,
        "round": 1,
        "position": 1,
        "manager_id": 7727371,
        "manager_name": "Ruben",
        "budgets": {},
        "spent": {},
        "squad_counts": {},
        "message": "turno de Ruben",
    }
    with patch(
        "packages.biwenger_tools.api.app.draft_service.get_state", return_value=fake
    ) as mock_run:
        resp = client.get("/draft/state")
    mock_run.assert_called_once()
    assert resp.status_code == 200
    assert resp.get_json() == fake


def test_draft_state_returns_500_on_exception(client):
    with patch(
        "packages.biwenger_tools.api.app.draft_service.get_state",
        side_effect=RuntimeError("boom"),
    ):
        resp = client.get("/draft/state")
    assert resp.status_code == 500
    assert resp.get_json()["completed"] is False


def test_draft_state_rejects_post(client):
    resp = client.post("/draft/state")
    assert resp.status_code == 405


def test_draft_pick_calls_service(client):
    fake = {
        "status": "applied",
        "message": "ok",
        "player": {},
        "remaining": 0,
        "next_manager": "Javi",
    }
    with patch(
        "packages.biwenger_tools.api.app.draft_service.submit_pick",
        return_value=fake,
    ) as mock_run:
        resp = client.post(
            "/draft/pick", json={"telegram_user_id": "1", "query": "messi"}
        )
    mock_run.assert_called_once_with("1", "messi")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "applied"


def test_draft_pick_rejects_missing_fields(client):
    resp = client.post("/draft/pick", json={"telegram_user_id": "1"})
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "rejected"


def test_draft_pick_returns_500_on_exception(client):
    with patch(
        "packages.biwenger_tools.api.app.draft_service.submit_pick",
        side_effect=RuntimeError("boom"),
    ):
        resp = client.post(
            "/draft/pick", json={"telegram_user_id": "1", "query": "messi"}
        )
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "INTERNAL_ERROR"


def test_draft_pick_rejects_get(client):
    resp = client.get("/draft/pick")
    assert resp.status_code == 405


def test_draft_pick_confirm_calls_service(client):
    fake = {
        "status": "applied",
        "message": "ok",
        "player": {},
        "remaining": 0,
        "next_manager": "Javi",
    }
    with patch(
        "packages.biwenger_tools.api.app.draft_service.confirm_pick",
        return_value=fake,
    ) as mock_run:
        resp = client.post(
            "/draft/pick/confirm", json={"telegram_user_id": "1", "player_id": 42}
        )
    mock_run.assert_called_once_with("1", 42)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "applied"


def test_draft_pick_confirm_rejects_non_int_player_id(client):
    resp = client.post(
        "/draft/pick/confirm", json={"telegram_user_id": "1", "player_id": "abc"}
    )
    assert resp.status_code == 400


def test_draft_pick_confirm_rejects_missing_fields(client):
    resp = client.post("/draft/pick/confirm", json={"telegram_user_id": "1"})
    assert resp.status_code == 400


def test_draft_undo_calls_service(client):
    fake = {"status": "reverted", "message": "listo"}
    with patch(
        "packages.biwenger_tools.api.app.draft_service.undo_last_pick",
        return_value=fake,
    ) as mock_run:
        resp = client.post("/draft/undo", json={"telegram_user_id": "999"})
    mock_run.assert_called_once_with("999")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "reverted"


def test_draft_undo_rejects_missing_telegram_id(client):
    resp = client.post("/draft/undo", json={})
    assert resp.status_code == 400


def test_draft_undo_returns_500_on_exception(client):
    with patch(
        "packages.biwenger_tools.api.app.draft_service.undo_last_pick",
        side_effect=RuntimeError("boom"),
    ):
        resp = client.post("/draft/undo", json={"telegram_user_id": "999"})
    assert resp.status_code == 500


def test_draft_export_calls_service(client):
    fake = {"message": "3 fichajes", "picks": [{"player_id": 1}]}
    with patch(
        "packages.biwenger_tools.api.app.draft_service.export_picks",
        return_value=fake,
    ) as mock_run:
        resp = client.get("/draft/export")
    mock_run.assert_called_once()
    assert resp.status_code == 200
    assert resp.get_json() == fake


def test_draft_export_returns_500_on_exception(client):
    with patch(
        "packages.biwenger_tools.api.app.draft_service.export_picks",
        side_effect=RuntimeError("boom"),
    ):
        resp = client.get("/draft/export")
    assert resp.status_code == 500
    assert resp.get_json()["picks"] == []


def test_draft_export_rejects_post(client):
    resp = client.post("/draft/export")
    assert resp.status_code == 405


# --- /periodico/portada ---


def test_portada_route_passes_the_attachment_to_the_logic(client):
    with patch(
        "packages.biwenger_tools.api.app.periodico.publish_portada",
        return_value={"published": True, "message": "ok"},
    ) as mock_publish:
        resp = client.post(
            "/periodico/portada",
            json={
                "file_id": "f-1",
                "caption": "2026-08-14 Titular",
                "kind": "document",
            },
        )

    assert resp.status_code == 200
    assert resp.get_json()["message"] == "ok"
    mock_publish.assert_called_once_with(
        file_id="f-1", caption="2026-08-14 Titular", kind="document"
    )


def test_portada_route_requires_a_file_id(client):
    resp = client.post("/periodico/portada", json={"caption": "Titular"})
    assert resp.status_code == 400


def test_portada_route_answers_200_when_the_front_page_is_rejected(client):
    """A missing headline is the operator's to fix — the bot relays the
    instructions, so it must not arrive dressed as an error."""
    with patch(
        "packages.biwenger_tools.api.app.periodico.publish_portada",
        return_value={
            "published": False,
            "message": "❌ La portada necesita un titular.",
        },
    ):
        resp = client.post("/periodico/portada", json={"file_id": "f-1", "caption": ""})

    assert resp.status_code == 200
    assert resp.get_json()["published"] is False


def test_portada_route_reports_a_write_failure_as_500(client):
    with patch(
        "packages.biwenger_tools.api.app.periodico.publish_portada",
        side_effect=RuntimeError("403 Forbidden"),
    ):
        resp = client.post("/periodico/portada", json={"file_id": "f-1"})

    assert resp.status_code == 500
    assert "403" in resp.get_json()["error"]
