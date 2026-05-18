"""Biwenger API service — HTTP entry points for Telegram bot + Cloud Scheduler.

Skeleton in this PR: only /healthz and /version. The business-logic endpoints
(/teams, /lineups/auto-pick, /digests/daily, /budget/recommendations, etc.)
land in subsequent PRs as we move modes out of teams_analyzer.
"""

import os

from flask import Flask, jsonify

from core.utils import get_logger
from packages.biwenger_tools.api import config

logger = get_logger(__name__)

app = Flask(__name__)


@app.route("/healthz", methods=["GET"])
def healthz():
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
