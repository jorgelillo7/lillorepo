"""Gunicorn launcher for the Chuck Norris bot on Cloud Run."""

from core.serving.gunicorn import run

run("packages.chucknorris_bot.bot.app:app")
