"""Session and identity: nickname login, Google Sign-In, logout."""

import re

from flask import abort, redirect, request, session, url_for

from core.utils import get_logger
from core.web.csrf import verify_csrf_token
from packages.be_water.web import auth, config, helpers, repository

logger = get_logger(__name__)


def login():
    if not verify_csrf_token() or not helpers.LOGIN_LIMITER.allow(helpers.client_ip()):
        return redirect(request.referrer or url_for("index"))
    nickname = (request.form.get("nickname") or "").strip().lower()
    if not helpers.NICKNAME_RE.match(nickname):
        return redirect(request.referrer or url_for("index"))
    user = repository.get_user(nickname)
    if user and user.get("blocked"):
        return redirect(request.referrer or url_for("index"))
    repository.touch_user(nickname)
    session["nickname"] = nickname
    return redirect(request.referrer or url_for("index"))


def google_login():
    """GIS login_uri target: Google's double-submit cookie replaces our
    session CSRF here (the POST is minted by the GIS script, which has no
    access to our form token)."""
    if not config.GOOGLE_CLIENT_ID:
        abort(404)
    if not helpers.LOGIN_LIMITER.allow(helpers.client_ip()):
        return redirect(url_for("index"))
    body_token = request.form.get("g_csrf_token", "")
    cookie_token = request.cookies.get("g_csrf_token", "")
    if not body_token or body_token != cookie_token:
        abort(403)
    try:
        identity = auth.verify_google_credential(request.form.get("credential", ""))
    except auth.GoogleAuthError as exc:
        logger.warning("Google Sign-In rejected.", extra={"error": str(exc)[:200]})
        return redirect(url_for("index"))
    session["google_email"] = identity["email"]
    session["google_name"] = identity["name"]
    # Google identity doubles as contributor identity: derive a nickname
    # so signed-in users can favorite/add without the nick prompt.
    if not session.get("nickname"):
        derived = re.sub(r"[^a-z0-9_-]", "-", identity["email"].split("@")[0].lower())
        derived = derived[:20].strip("-") or "user"
        user = repository.get_user(derived)
        if not (user and user.get("blocked")):
            repository.touch_user(derived)
            session["nickname"] = derived
    return redirect(url_for("admin_page") if helpers.is_admin() else url_for("index"))


def logout():
    if verify_csrf_token():
        session.pop("nickname", None)
        session.pop("google_email", None)
        session.pop("google_name", None)
    return redirect(url_for("index"))


def register(app):
    app.add_url_rule("/login", "login", login, methods=["POST"])
    app.add_url_rule("/auth/google", "google_login", google_login, methods=["POST"])
    app.add_url_rule("/logout", "logout", logout, methods=["POST"])
