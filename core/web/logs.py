"""Flask's own log lines as JSON Cloud Logging can grade."""

from flask import Flask
from flask.logging import default_handler

from core.utils import get_logger


def use_json_logging(app: Flask) -> Flask:
    """Replace Flask's default handler with the JSON one `get_logger` uses.

    Flask logs an unhandled exception through `app.logger`, whose default
    handler writes raw text to `wsgi.errors`: Cloud Logging split each
    traceback into many DEFAULT entries. Afterwards it is one ERROR line.
    """
    app.logger.removeHandler(default_handler)
    get_logger(app.logger.name)
    return app
