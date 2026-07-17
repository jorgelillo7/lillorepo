"""Gunicorn launcher for be-water on Cloud Run.

Relies on PYTHONPATH=/app set by entrypoint.sh, so the canonical module path
`packages.be_water.web.app:app` resolves without sys.path tricks.
"""

import sys

from gunicorn.app.wsgiapp import run

if __name__ == "__main__":
    sys.argv = [
        "gunicorn",
        "--bind",
        "0.0.0.0:8080",
        "packages.be_water.web.app:app",
    ]
    run()
