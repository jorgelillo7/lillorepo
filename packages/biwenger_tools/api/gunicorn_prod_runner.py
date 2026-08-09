"""Gunicorn launcher for the Biwenger API service on Cloud Run."""

from core.serving.gunicorn import run

run("packages.biwenger_tools.api.app:app", timeout=180)
