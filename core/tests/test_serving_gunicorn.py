"""Tests for `core.serving.gunicorn.run`."""

import json
import logging
import sys
from unittest.mock import patch

import pytest

from core.serving import gunicorn


@pytest.fixture(autouse=True)
def _restore_argv():
    """`run` assigns `sys.argv` for gunicorn to parse. Left as-is it would
    outlive the test and reach whatever runs next in the same process."""
    original = sys.argv
    yield
    sys.argv = original


def test_run_without_timeout_omits_the_flag():
    """A service with no long-running handlers keeps gunicorn's own default."""
    with patch("core.serving.gunicorn._run"):
        gunicorn.run("packages.chucknorris_bot.bot.app:app")
    assert sys.argv == [
        "gunicorn",
        "--bind",
        "0.0.0.0:8080",
        "--config",
        "python:core.serving.gunicorn_conf",
        "packages.chucknorris_bot.bot.app:app",
    ]


def test_run_with_timeout_adds_the_flag_before_the_app_path():
    """gunicorn parses argv positionally — the app path must stay last."""
    with patch("core.serving.gunicorn._run"):
        gunicorn.run("packages.biwenger_tools.api.app:app", timeout=180)
    assert sys.argv == [
        "gunicorn",
        "--bind",
        "0.0.0.0:8080",
        "--config",
        "python:core.serving.gunicorn_conf",
        "--timeout",
        "180",
        "packages.biwenger_tools.api.app:app",
    ]


def test_run_invokes_gunicorns_own_entrypoint():
    """`run` must not just build argv — it has to actually hand off to gunicorn."""
    with patch("core.serving.gunicorn._run") as mock_run:
        gunicorn.run("packages.biwenger_tools.bot.app:app", timeout=180)
    mock_run.assert_called_once_with()


@pytest.fixture
def _restore_logging():
    """Gunicorn's dictConfig rewires process-wide loggers; put them back."""
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    error = logging.getLogger("gunicorn.error")
    saved_error = (list(error.handlers), error.level, error.propagate)
    yield
    root.handlers[:], root.level = saved
    error.handlers[:], error.level, error.propagate = saved_error


def _gunicorn_logger():
    from gunicorn.config import Config
    from gunicorn.glogging import Logger

    from core.serving import gunicorn_conf

    cfg = Config()
    cfg.set("logconfig_dict", gunicorn_conf.logconfig_dict)
    return Logger(cfg)


def test_gunicorn_lines_are_json_with_severity(capsys, _restore_logging):
    """A worker timeout is gunicorn's own CRITICAL line; as plain text Cloud
    Logging filed it as DEFAULT, invisible to `severity>=ERROR`."""
    _gunicorn_logger().critical("WORKER TIMEOUT (pid:%s)", 7)
    line = json.loads(capsys.readouterr().err.strip().splitlines()[-1])
    assert line["severity"] == "CRITICAL"
    assert line["message"] == "WORKER TIMEOUT (pid:7)"


def test_gunicorn_config_adds_no_root_handler(capsys, _restore_logging):
    """gunicorn's defaults give root a stdout handler; `get_logger` loggers
    propagate, so keeping it would print every application line twice."""
    from core import utils

    _gunicorn_logger()
    utils.get_logger("no-duplicate-test").error("once")
    captured = capsys.readouterr()
    assert "once" not in captured.out


def test_gunicorn_access_lines_stay_off(capsys, _restore_logging):
    """Any `logconfig_dict` switches gunicorn's access log on; Cloud Run
    already writes a request log, so it would only double the volume."""
    _gunicorn_logger()
    logging.getLogger("gunicorn.access").info('"GET /health HTTP/1.1" 200')
    captured = capsys.readouterr()
    assert "GET /health" not in captured.out + captured.err
