"""Gunicorn launcher for the Biwenger API service on Cloud Run."""

import sys

from gunicorn.app.wsgiapp import run

if __name__ == "__main__":
    sys.argv = [
        "gunicorn",
        "--bind",
        "0.0.0.0:8080",
        "packages.biwenger_tools.api.app:app",
    ]
    run()
