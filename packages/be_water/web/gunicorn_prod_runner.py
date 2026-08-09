"""Gunicorn launcher for be-water on Cloud Run.

Relies on PYTHONPATH=/app set by entrypoint.sh, so the canonical module path
`packages.be_water.web.app:app` resolves without sys.path tricks.
"""

from core.serving.gunicorn import run

run("packages.be_water.web.app:app")
