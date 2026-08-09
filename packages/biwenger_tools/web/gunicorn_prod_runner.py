"""Gunicorn launcher for the web app on Cloud Run.

Relies on PYTHONPATH=/app set by entrypoint.sh, so the canonical module path
`packages.biwenger_tools.web.app:app` resolves without sys.path tricks.
"""

from core.serving.gunicorn import run

run("packages.biwenger_tools.web.app:app")
