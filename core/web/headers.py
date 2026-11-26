"""Baseline security headers for the public Flask apps, and their CSP."""

import base64
import hashlib
import re
import secrets
from pathlib import Path

from flask import Flask, Response, g, request

from core.utils import get_logger
from core.web.ratelimit import RateLimiter, client_ip

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # None of the apps asks for these; a script injected into one could not either.
    "Permissions-Policy": (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=(), "
        "serial=(), bluetooth=()"
    ),
    # Its own browsing context group, so a page that opened ours cannot reach it;
    # allow-popups because be_water signs in through Google's popup.
    "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
}
CSP_REPORT_PATH = "/csp-report"

logger = get_logger(__name__)
_REPORT_LIMITER = RateLimiter(30, 60)


def csp_nonce() -> str:
    """This request's nonce: every inline <script> carries it, nothing else runs."""
    if "csp_nonce" not in g:
        g.csp_nonce = secrets.token_urlsafe(18)
    return g.csp_nonce


def style_hashes(html_file: str | Path) -> list[str]:
    """CSP sources (`'sha256-…'`) for every <style> block in a static HTML file.

    For pages served as files, such as the offline page a service worker
    caches, which cannot carry a per-request nonce.
    """
    html = Path(html_file).read_text(encoding="utf-8")
    blocks = re.findall(r"<style[^>]*>(.*?)</style>", html, flags=re.S)
    return [
        "'sha256-"
        + base64.b64encode(hashlib.sha256(b.encode()).digest()).decode()
        + "'"
        for b in blocks
    ]


def _policy_header(policy: dict[str, list[str]]) -> str:
    directives = [
        f"{name} {' '.join(sources)}".replace("{nonce}", csp_nonce())
        for name, sources in policy.items()
    ]
    directives.append(f"report-uri {CSP_REPORT_PATH}")
    return "; ".join(directives)


def add_security_headers(app: Flask, csp: dict[str, list[str]] | None = None) -> Flask:
    """Set each header on every response unless the route already chose one.

    HSTS pins HTTPS for a year (no `includeSubDomains`: the host is a shared
    run.app name); nosniff stops MIME guessing; DENY keeps the pages out of
    other sites' frames; the referrer policy sends only the origin elsewhere;
    Permissions-Policy turns off device APIs no app uses; COOP isolates the window.

    With `csp`, a Content-Security-Policy too: `'nonce-{nonce}'` in a source
    list becomes this request's nonce (`csp_nonce()` in templates), and the
    browser reports what it blocks to `/csp-report`, logged as a WARNING.
    """
    if csp is not None:
        app.add_template_global(csp_nonce, "csp_nonce")
        app.add_url_rule(CSP_REPORT_PATH, "csp_report", _csp_report, methods=["POST"])

    @app.after_request
    def _security_headers(response):
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if csp is not None:
            response.headers.setdefault("Content-Security-Policy", _policy_header(csp))
        return response

    return app


def _csp_report() -> Response:
    """Log what the browser blocked; 204 either way, it never retries."""
    if _REPORT_LIMITER.allow(client_ip()):
        report = (request.get_json(force=True, silent=True) or {}).get("csp-report", {})
        logger.warning(
            "CSP blocked a source.",
            extra={
                "blocked_uri": report.get("blocked-uri"),
                "violated_directive": report.get("violated-directive"),
                "document_uri": report.get("document-uri"),
                "source_file": report.get("source-file"),
                "line_number": report.get("line-number"),
            },
        )
    return Response(status=204)


def harden_session_cookie(app: Flask) -> Flask:
    """Name the session cookie `__Host-session` when it is Secure.

    The prefix makes the browser refuse the cookie unless it is Secure, has
    `Path=/` and no `Domain`, so no sibling `*.run.app` site can plant or shadow
    it. Local HTTP development (`SESSION_COOKIE_SECURE` off) keeps Flask's name,
    which a browser would otherwise drop.
    """
    if app.config.get("SESSION_COOKIE_SECURE"):
        app.config.update(
            SESSION_COOKIE_NAME="__Host-session",
            SESSION_COOKIE_PATH="/",
            SESSION_COOKIE_DOMAIN=None,
        )
    return app
