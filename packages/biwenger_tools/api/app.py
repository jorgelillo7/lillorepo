"""Biwenger API service — HTTP entry points for Telegram bot + Cloud Scheduler.

Each route is a thin shell that delegates to `logic/`. Most routes have a
side effect (PNG/message to Telegram); we still call them GET when the
endpoint only *reads* from Biwenger/JP, and POST when it mutates external
state (Biwenger lineup PUT, daily cron tick).
"""

import os

from flask import Flask, jsonify, request

from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import (
    actions,
    auto_bid,
    digests,
    emergency,
    offers,
    recommendations,
    scraper,
)

logger = get_logger(__name__)

app = Flask(__name__)


def _run_action(name: str, fn):
    try:
        result = fn()
        return jsonify({"status": "ok", **result}), 200
    except Exception as exc:
        logger.exception("%s failed.", name)
        return jsonify({"status": "error", "error": str(exc)}), 500


# --- Liveness / metadata ---------------------------------------------------


@app.route("/health", methods=["GET"])
def health():
    # Do NOT use "/healthz" — Google Frontend reserves that path on *.run.app
    # and returns its own 404 before the request reaches the container.
    return jsonify({"status": "ok"}), 200


@app.route("/version", methods=["GET"])
def version():
    return (
        jsonify(
            {
                "service": "biwenger-api",
                "commit": config.GIT_COMMIT or "unknown",
                "deploy_time": config.DEPLOY_TIME or "",
            }
        ),
        200,
    )


# --- Bot-triggered endpoints ----------------------------------------------


@app.route("/teams", methods=["GET"])
def teams():
    """Squad images to Telegram.

    Query params:
      - `manager=<int>` — only that manager's squad (no market block).
      - omitted (or `manager=all`) — every manager + market (the
        original `/analizar` flow).
    """
    manager_arg = request.args.get("manager")
    manager_id: int | None
    if manager_arg in (None, "", "all"):
        manager_id = None
    else:
        try:
            manager_id = int(manager_arg)
        except (TypeError, ValueError):
            return (
                jsonify({"status": "error", "error": "manager must be an integer"}),
                400,
            )
    return _run_action("teams", lambda: actions.run_teams(manager_id))


@app.route("/managers", methods=["GET"])
def managers():
    """League managers — used by the bot's `/analizar` picker."""
    return _run_action("managers", actions.list_managers)


@app.route("/market", methods=["GET"])
def market():
    """Transfer market only — was /mercado."""
    return _run_action("market", actions.run_market)


@app.route("/lineups/auto-pick", methods=["POST"])
def lineups_auto_pick():
    """Pick best lineup, apply on Biwenger, confirm via Telegram — was /alinear.

    Query param `dry_run=1` previews the lineup without doing the
    Biwenger PUT — sends the same Telegram message but tagged "Preview".
    """
    dry_run_raw = (request.args.get("dry_run") or "").strip().lower()
    dry_run = dry_run_raw in ("1", "true", "yes")
    return _run_action(
        "lineups.auto-pick", lambda: actions.run_auto_pick_lineup(dry_run=dry_run)
    )


@app.route("/budget/recommendations", methods=["GET"])
def budget_recommendations():
    """Top-N affordable clausulazo targets per position.

    Query params:
      - `top=N`     — players per position, 1–10, default 3.
      - `margin=N`  — fixed extra euros over current cash to count as
                       "affordable", 0–50M. **If omitted, a dynamic margin
                       is computed from cash** (see compute_dynamic_margin).
    """
    try:
        top = int(request.args.get("top", recommendations.DEFAULT_TOP_N))
    except (TypeError, ValueError):
        top = recommendations.DEFAULT_TOP_N
    top = max(1, min(10, top))

    margin_arg = request.args.get("margin")
    if margin_arg is None:
        margin = None  # dynamic
    else:
        try:
            margin = max(0, min(50_000_000, int(margin_arg)))
        except (TypeError, ValueError):
            margin = None  # fall back to dynamic on garbage

    return _run_action(
        "budget.recommendations",
        lambda: recommendations.run_recommendations(top=top, margin=margin),
    )


@app.route("/scraper/trigger", methods=["POST"])
def scraper_trigger():
    """Queue an execution of the scraper Cloud Run Job — bot's /scrapper."""
    return _run_action("scraper.trigger", scraper.run_trigger_scraper)


@app.route("/emergency/clausulazo/preview", methods=["POST"])
def emergency_clausulazo_preview():
    """Compute the emergency target + post confirmation message — bot's /emergencia.

    Query params (set by the bot when the user taps a selector button
    after a multi-clausulazo run):
      - `force_position=<2|3|4>` — skip detection, lock target to that
        outfield position.
      - `force_weakest=1` — skip detection, target the weakest line.

    Side effect: one Telegram message (selector OR confirmation). The
    bot does not read the JSON response — the flow rides on the
    inline-keyboard callbacks the user taps.
    """
    force_position_raw = (request.args.get("force_position") or "").strip()
    force_weakest_raw = (request.args.get("force_weakest") or "").strip().lower()
    force_weakest = force_weakest_raw in ("1", "true", "yes")
    force_position: int | None
    if force_position_raw:
        try:
            force_position = int(force_position_raw)
        except ValueError:
            force_position = None
    else:
        force_position = None
    return _run_action(
        "emergency.preview",
        lambda: emergency.preview_clausulazo(
            force_position=force_position, force_weakest=force_weakest
        ),
    )


@app.route("/emergency/clausulazo/execute", methods=["POST"])
def emergency_clausulazo_execute():
    """Fire the approved clausulazo.

    Query params (passed by the bot from the inline-keyboard payload):
      - `player_id` — Biwenger player id to clause.
      - `owner_id` — current owner's user id (becomes `to` in the POST).
      - `amount` — euros (must be ≥ clause_value or Biwenger 4xxes).
    """
    try:
        player_id = int(request.args["player_id"])
        owner_id = int(request.args["owner_id"])
        amount = int(request.args["amount"])
    except (KeyError, TypeError, ValueError):
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "player_id, owner_id, amount required (int)",
                }
            ),
            400,
        )
    return _run_action(
        "emergency.execute",
        lambda: emergency.execute_clausulazo(
            player_id=player_id, owner_user_id=owner_id, amount=amount
        ),
    )


@app.route("/offers/inbox", methods=["POST"])
def offers_inbox():
    """List + score received offers, post one Telegram message per offer."""
    return _run_action("offers.inbox", offers.run_offers_inbox)


@app.route("/offers/decide", methods=["POST"])
def offers_decide():
    """Accept or reject a received offer.

    Query params:
      - `offer_id` (int, required)
      - `decision` (string, required; must be `accepted` or `rejected`)
    """
    try:
        offer_id = int(request.args["offer_id"])
    except (KeyError, TypeError, ValueError):
        return (
            jsonify({"status": "error", "error": "offer_id required (int)"}),
            400,
        )
    decision = (request.args.get("decision") or "").strip().lower()
    if decision not in offers.VALID_DECISIONS:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": (
                        "decision must be one of " f"{list(offers.VALID_DECISIONS)}"
                    ),
                }
            ),
            400,
        )
    return _run_action(
        "offers.decide",
        lambda: offers.run_offer_decision(offer_id=offer_id, decision=decision),
    )


# --- Scheduler-triggered endpoints -----------------------------------------


@app.route("/digests/daily", methods=["POST"])
def digests_daily():
    """Cron-triggered: send "my team + market" PNGs to Telegram."""
    return _run_action("digests.daily", digests.run_daily)


@app.route("/market/auto-bid", methods=["POST"])
def market_auto_bid():
    """Cron-triggered (09:00 Madrid): tiered auto-bid on the daily market.

    Idempotent across same-day retries — bids are logged to Firestore
    under `auto_bid_log/{date}/bids` and skipped on replay.
    """
    return _run_action("market.auto-bid", auto_bid.run_auto_bid)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
