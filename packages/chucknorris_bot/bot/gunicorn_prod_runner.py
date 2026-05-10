"""Gunicorn launcher for the Chuck Norris bot on Cloud Run."""

import sys

from gunicorn.app.wsgiapp import run

if __name__ == "__main__":
    sys.argv = [
        "gunicorn",
        "--bind",
        "0.0.0.0:8080",
        "packages.chucknorris_bot.bot.app:app",
    ]
    run()
