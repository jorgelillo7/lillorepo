"""Tests for `core.web.logs.use_json_logging`."""

import io
import json

from flask import Flask

from core.web.logs import use_json_logging


def test_an_unhandled_exception_is_one_json_error_line():
    """Flask's default handler writes the traceback as raw text to
    `wsgi.errors`; Cloud Logging split it into many DEFAULT entries."""
    app = Flask("json-logging-test")
    use_json_logging(app)
    stream = io.StringIO()
    app.logger.handlers[0].setStream(stream)

    @app.route("/boom")
    def boom():
        return 1 / 0

    response = app.test_client().get("/boom")

    assert response.status_code == 500
    lines = stream.getvalue().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["severity"] == "ERROR"
    assert "ZeroDivisionError" in entry["exc_info"]


def test_the_default_flask_handler_is_gone():
    from flask.logging import default_handler

    app = Flask("json-logging-handlers-test")
    use_json_logging(app)
    assert default_handler not in app.logger.handlers
    assert len(app.logger.handlers) == 1
