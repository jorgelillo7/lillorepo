"""Baseline security headers for the public Flask apps."""

from flask import Flask

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def add_security_headers(app: Flask) -> Flask:
    """Set each header on every response unless the route already chose one.

    HSTS pins HTTPS for a year (no `includeSubDomains`: the host is a shared
    run.app name); nosniff stops MIME guessing; DENY keeps the pages out of
    other sites' frames; the referrer policy sends only the origin elsewhere.
    """

    @app.after_request
    def _security_headers(response):
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    return app
