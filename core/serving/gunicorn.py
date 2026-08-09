"""Shared gunicorn launcher for every Cloud Run service in this repo."""

import sys

from gunicorn.app.wsgiapp import run as _run


def run(app_path: str, timeout: int | None = None) -> None:
    """Launch gunicorn bound to 0.0.0.0:8080, serving `app_path`.

    `app_path` is the WSGI target in `module.path:app` form. `timeout`, when
    given, raises the worker timeout past gunicorn's 30 s default — a handler
    that legitimately runs longer (chained external calls, heavy rendering,
    uploads) would otherwise get SIGKILLed before any Python `except` block
    can run, so the caller sees a silent 500 with no error message at all.
    """
    argv = ["gunicorn", "--bind", "0.0.0.0:8080"]
    if timeout is not None:
        argv += ["--timeout", str(timeout)]
    argv.append(app_path)
    sys.argv = argv
    _run()
