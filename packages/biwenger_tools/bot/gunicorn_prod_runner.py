"""Gunicorn launcher for the Biwenger bot service on Cloud Run."""

import sys

from gunicorn.app.wsgiapp import run

# Mirror the api runner's 180 s. The bot itself returns to Telegram in
# milliseconds (heavy work runs in a daemon thread), so the bump is purely
# a defensive margin: if a Telegram API call ever stalls, gunicorn won't
# kill the worker before the request's own timeout fires.
_WORKER_TIMEOUT_SECONDS = "180"

if __name__ == "__main__":
    sys.argv = [
        "gunicorn",
        "--bind",
        "0.0.0.0:8080",
        "--timeout",
        _WORKER_TIMEOUT_SECONDS,
        "packages.biwenger_tools.bot.app:app",
    ]
    run()
