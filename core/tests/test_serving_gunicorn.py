"""Tests for `core.serving.gunicorn.run`."""

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
        "--timeout",
        "180",
        "packages.biwenger_tools.api.app:app",
    ]


def test_run_invokes_gunicorns_own_entrypoint():
    """`run` must not just build argv — it has to actually hand off to gunicorn."""
    with patch("core.serving.gunicorn._run") as mock_run:
        gunicorn.run("packages.biwenger_tools.bot.app:app", timeout=180)
    mock_run.assert_called_once_with()
