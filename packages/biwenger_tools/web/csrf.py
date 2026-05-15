"""CSRF token helpers for Flask form POSTs.

Tokens live in the signed session cookie. Templates pull the current token
via `{{ csrf_token() }}` (registered as a context processor in app.py).
POST handlers gate themselves with `verify_csrf_token()`.

A handwritten implementation is enough for our two admin forms; adding
Flask-WTF for this would be more dependency than logic.
"""

import hmac
import secrets

from flask import request, session


def get_csrf_token() -> str:
    """Return the per-session CSRF token, creating it on first access."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def verify_csrf_token() -> bool:
    """Constant-time check of the submitted csrf_token form field."""
    submitted = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not submitted or not expected:
        return False
    return hmac.compare_digest(submitted, expected)
