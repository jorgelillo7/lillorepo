"""core.web — CSRF helpers and the in-process rate limiter."""

import time

from flask import Flask, session

from core.web.csrf import get_csrf_token, verify_csrf_token
from core.web.ratelimit import RateLimiter


def _app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "test"
    return app


def test_csrf_token_is_stable_per_session():
    with _app().test_request_context("/"):
        first = get_csrf_token()
        assert first == get_csrf_token()
        assert len(first) > 20


def test_verify_rejects_missing_and_wrong_token():
    app = _app()
    with app.test_request_context("/", method="POST", data={}):
        assert not verify_csrf_token()
    with app.test_request_context("/", method="POST", data={"csrf_token": "x"}):
        session["csrf_token"] = "y"
        assert not verify_csrf_token()


def test_verify_accepts_matching_token():
    with _app().test_request_context("/", method="POST", data={"csrf_token": "tok"}):
        session["csrf_token"] = "tok"
        assert verify_csrf_token()


def test_rate_limiter_blocks_then_recovers():
    limiter = RateLimiter(2, 0.05)
    assert limiter.allow("ip")
    assert limiter.allow("ip")
    assert not limiter.allow("ip")
    assert limiter.allow("other-ip")  # keys are independent
    time.sleep(0.06)
    assert limiter.allow("ip")  # window slid


def test_rate_limiter_reset():
    limiter = RateLimiter(1, 60)
    assert limiter.allow("ip")
    assert not limiter.allow("ip")
    limiter.reset()
    assert limiter.allow("ip")
