"""Gunicorn launcher for the Biwenger API service on Cloud Run."""

import sys

from gunicorn.app.wsgiapp import run

# Worker timeout in seconds. Default (30 s) is too tight for handlers that
# chain JP + Biwenger fetches, matplotlib rendering and Telegram uploads:
# /digests/daily and /lineups/auto-pick can sit on `requests.post` past 30 s
# under load. When that happens gunicorn sends SIGKILL to the worker before
# any Python `except` block can surface the failure — the user gets no
# message, just a silent 500. Cloud Run caps requests at 60 min by default,
# so 180 s is generous without leaving runaway requests blocking instances.
_WORKER_TIMEOUT_SECONDS = "180"

if __name__ == "__main__":
    sys.argv = [
        "gunicorn",
        "--bind",
        "0.0.0.0:8080",
        "--timeout",
        _WORKER_TIMEOUT_SECONDS,
        "packages.biwenger_tools.api.app:app",
    ]
    run()
