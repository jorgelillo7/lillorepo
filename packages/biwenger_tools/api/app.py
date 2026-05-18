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
from packages.biwenger_tools.api.logic import actions, digests, recommendations

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
    """All managers + market — was /analizar."""
    return _run_action("teams", actions.run_all_teams)


@app.route("/teams/mine", methods=["GET"])
def teams_mine():
    """My squad only — was /myteam."""
    return _run_action("teams.mine", actions.run_my_team)


@app.route("/market", methods=["GET"])
def market():
    """Transfer market only — was /mercado."""
    return _run_action("market", actions.run_market)


@app.route("/lineups/auto-pick", methods=["POST"])
def lineups_auto_pick():
    """Pick best lineup, apply on Biwenger, confirm via Telegram — was /alinear."""
    return _run_action("lineups.auto-pick", actions.run_auto_pick_lineup)


@app.route("/budget/recommendations", methods=["GET"])
def budget_recommendations():
    """Top-N affordable clausulazo targets per position. New endpoint.

    Query: `?top=N` (1–10, default 3).
    """
    try:
        top = int(request.args.get("top", recommendations.DEFAULT_TOP_N))
    except (TypeError, ValueError):
        top = recommendations.DEFAULT_TOP_N
    top = max(1, min(10, top))
    return _run_action(
        "budget.recommendations", lambda: recommendations.run_recommendations(top=top)
    )


# --- Scheduler-triggered endpoints -----------------------------------------


@app.route("/digests/daily", methods=["POST"])
def digests_daily():
    """Cron-triggered: send "my team + market" PNGs to Telegram."""
    return _run_action("digests.daily", digests.run_daily)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
