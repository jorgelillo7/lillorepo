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


def test_security_headers_on_every_response():
    """HSTS, no MIME sniffing, no framing, no full-URL referrers."""
    from core.web.headers import add_security_headers

    app = add_security_headers(_app())

    @app.route("/")
    def home():
        return "ok"

    headers = app.test_client().get("/").headers
    assert headers["Strict-Transport-Security"] == "max-age=31536000"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_security_headers_do_not_override_a_route_choice():
    from core.web.headers import add_security_headers

    app = add_security_headers(_app())

    @app.route("/embed")
    def embed():
        return "ok", 200, {"X-Frame-Options": "SAMEORIGIN"}

    assert app.test_client().get("/embed").headers["X-Frame-Options"] == "SAMEORIGIN"


_POLICY = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "'nonce-{nonce}'", "https://cdn.example"],
    "object-src": ["'none'"],
}


def _csp_app():
    from core.web.headers import add_security_headers

    app = add_security_headers(_app(), csp=_POLICY)

    @app.route("/")
    def home():
        from flask import render_template_string

        return render_template_string("<script nonce='{{ csp_nonce() }}'></script>")

    return app


def test_csp_nonce_in_header_matches_the_page():
    """Only a <script> carrying this request's nonce may run."""
    import re

    response = _csp_app().test_client().get("/")
    header = response.headers["Content-Security-Policy"]
    nonce = re.search(r"'nonce-([^']+)'", header).group(1)
    assert f"nonce='{nonce}'" in response.get_data(as_text=True)
    assert len(nonce) >= 16
    assert "object-src 'none'" in header
    assert "report-uri /csp-report" in header


def test_csp_nonce_changes_every_request():
    import re

    client = _csp_app().test_client()
    first, second = (
        re.search(
            r"'nonce-([^']+)'", client.get("/").headers["Content-Security-Policy"]
        ).group(1)
        for _ in range(2)
    )
    assert first != second


def test_csp_report_is_logged_as_a_warning(caplog):
    """A blocked source in production shows up in Cloud Logging instead of as
    a silently broken page."""
    import logging

    report = {
        "csp-report": {
            "blocked-uri": "https://evil.example/x.js",
            "violated-directive": "script-src",
            "document-uri": "https://x/",
        }
    }
    with caplog.at_level(logging.WARNING):
        response = (
            _csp_app()
            .test_client()
            .post("/csp-report", json=report, content_type="application/csp-report")
        )
    assert response.status_code == 204
    assert any(
        "evil.example" in str(getattr(r, "blocked_uri", "")) for r in caplog.records
    )


def test_no_csp_unless_asked():
    from core.web.headers import add_security_headers

    app = add_security_headers(_app())

    @app.route("/")
    def home():
        return "ok"

    assert "Content-Security-Policy" not in app.test_client().get("/").headers
