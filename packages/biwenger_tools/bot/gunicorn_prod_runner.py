"""Gunicorn launcher for the Biwenger bot service on Cloud Run."""

from core.serving.gunicorn import run

run("packages.biwenger_tools.bot.app:app", timeout=180)
