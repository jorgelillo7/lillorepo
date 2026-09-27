"""core.web — CSRF helpers and the in-process rate limiter."""

import time

from flask import Flask, session

from core.web.csrf import get_csrf_token, verify_csrf_token
from core.web.ratelimit import RateLimiter, client_ip


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


def test_client_ip_is_the_address_cloud_run_appended():
    """Cloud Run appends the connecting address to X-Forwarded-For; anything
    before it came from the client. Keying on the first entry let a new
    spoofed value per request walk past every limiter."""
    headers = {"X-Forwarded-For": "6.6.6.6, 203.0.113.9"}
    with _app().test_request_context("/", headers=headers):
        assert client_ip() == "203.0.113.9"


def test_client_ip_without_the_header_is_the_peer():
    with _app().test_request_context("/", environ_base={"REMOTE_ADDR": "10.0.0.7"}):
        assert client_ip() == "10.0.0.7"
