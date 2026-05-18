"""Biwenger API service — HTTP entry points for Telegram bot + Cloud Scheduler.

PR 1 scaffold: /health and /version.
PR 2 (this): adds POST /digests/daily for the cron.
"""

import os

from flask import Flask, jsonify

from core.utils import get_logger
from packages.biwenger_tools.api import config
from packages.biwenger_tools.api.logic import digests

logger = get_logger(__name__)

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    # Note: do NOT use "/healthz" — Google Frontend reserves that path on
    # *.run.app and returns its own 404 before the request reaches the
    # container. "/health" works.
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


@app.route("/digests/daily", methods=["POST"])
def digests_daily():
    """Cron-triggered: send "my team + market" PNGs to Telegram.

    Cloud Scheduler hits this once a day with an OIDC token. The Biwenger
    + JP traffic is real (no preview mode), so this should only ever be
    called by the Scheduler.
    """
    try:
        result = digests.run_daily()
        return jsonify({"status": "ok", **result}), 200
    except Exception as exc:
        logger.exception("Daily digest failed.")
        return jsonify({"status": "error", "error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
