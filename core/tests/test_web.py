"""core.web — CSRF helpers, the in-process rate limiter and versioned static URLs."""

import base64
import gzip
import hashlib
import time

from flask import Flask, session, url_for

from core.web.compress import compress_responses
from core.web.csrf import get_csrf_token, verify_csrf_token
from core.web.headers import add_security_headers, harden_session_cookie, style_hashes
from core.web.ratelimit import RateLimiter, client_ip
from core.web.static import IMMUTABLE, version_static_urls


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


def _static_app(tmp_path):
    (tmp_path / "logo.png").write_bytes(b"one")
    app = Flask(__name__, static_folder=str(tmp_path), static_url_path="/static")
    return version_static_urls(app)


def test_static_urls_carry_a_hash_of_the_file(tmp_path):
    app = _static_app(tmp_path)
    with app.test_request_context("/"):
        url = url_for("static", filename="logo.png")
        assert url.startswith("/static/logo.png?v=")
        assert url_for("static", filename="missing.png") == "/static/missing.png"


def test_a_versioned_static_request_is_cached_for_good(tmp_path):
    app = _static_app(tmp_path)
    with app.test_request_context("/"):
        url = url_for("static", filename="logo.png")
    client = app.test_client()
    assert client.get(url).headers["Cache-Control"] == IMMUTABLE
    # No version, or one that no longer matches the file: revalidate as before.
    assert client.get("/static/logo.png").headers.get("Cache-Control") != IMMUTABLE
    stale = client.get("/static/logo.png?v=000000000000")
    assert stale.headers.get("Cache-Control") != IMMUTABLE


def _text_app() -> Flask:
    app = compress_responses(Flask(__name__))

    @app.route("/big")
    def big():
        return "<p>hola</p>" * 500

    @app.route("/small")
    def small():
        return "<p>hola</p>"

    @app.route("/data")
    def data():
        return {"rows": list(range(1000))}

    @app.route("/png")
    def png():
        return app.response_class(b"\x89PNG" + b"0" * 5000, mimetype="image/png")

    return app


def test_text_over_1kib_is_gzipped_when_accepted():
    client = _text_app().test_client()
    for path in ("/big", "/data"):
        response = client.get(path, headers={"Accept-Encoding": "gzip"})
        assert response.headers["Content-Encoding"] == "gzip"
        assert "Accept-Encoding" in response.headers["Vary"]
        plain = client.get(path)
        assert gzip.decompress(response.data) == plain.data


def test_small_bodies_images_and_clients_without_gzip_are_left_alone():
    client = _text_app().test_client()
    assert "Content-Encoding" not in client.get("/big").headers
    small = client.get("/small", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in small.headers
    assert "Accept-Encoding" in small.headers["Vary"]
    image = client.get("/png", headers={"Accept-Encoding": "gzip"})
    assert "Content-Encoding" not in image.headers


def test_every_response_carries_permissions_policy_and_coop():
    app = add_security_headers(Flask(__name__))
    app.add_url_rule("/", "home", lambda: "ok")
    headers = app.test_client().get("/").headers
    assert "camera=()" in headers["Permissions-Policy"]
    assert "geolocation=()" in headers["Permissions-Policy"]
    # Chrome removed the Topics API and warns on every page that names it.
    assert "browsing-topics" not in headers["Permissions-Policy"]
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin-allow-popups"


def test_a_secure_session_cookie_takes_the_host_prefix_and_plain_http_does_not():
    secure = Flask(__name__)
    secure.config["SESSION_COOKIE_SECURE"] = True
    harden_session_cookie(secure)
    assert secure.config["SESSION_COOKIE_NAME"] == "__Host-session"
    assert secure.config["SESSION_COOKIE_PATH"] == "/"
    local = Flask(__name__)
    local.config["SESSION_COOKIE_SECURE"] = False
    harden_session_cookie(local)
    assert local.config["SESSION_COOKIE_NAME"] == "session"


def test_style_hashes_cover_each_style_block_of_a_static_page(tmp_path):
    page = tmp_path / "offline.html"
    page.write_text(
        '<style>body{color:red}</style><p>x</p><style media="print">p{}</style>'
    )
    # sha256 of the exact text between the tags, base64, as browsers compute it.
    assert style_hashes(page) == [
        "'sha256-FcQqt3aNlV7AZnGV4zkQRVeCeJOxbMPnQSx258L803E='",
        "'sha256-" + _b64_sha256(b"p{}") + "'",
    ]


def _b64_sha256(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()
