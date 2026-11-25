"""Session and identity: nickname login, Google Sign-In, logout."""

import re

from flask import abort, flash, redirect, request, session, url_for

from core.utils import get_logger
from core.web.csrf import verify_csrf_token
from core.web.ratelimit import client_ip
from packages.be_water.web import auth, config, helpers, repository

logger = get_logger(__name__)


def login():
    if not verify_csrf_token() or not helpers.LOGIN_LIMITER.allow(client_ip()):
        return redirect(request.referrer or url_for("index"))
    nickname = (request.form.get("nickname") or "").strip().lower()
    if not helpers.NICKNAME_RE.match(nickname):
        return redirect(request.referrer or url_for("index"))
    user = repository.get_user(nickname)
    if user and user.get("blocked"):
        return redirect(request.referrer or url_for("index"))
    if user and user.get("google_email"):
        # A linked nickname belongs to its Google account: typing it is not enough.
        flash(
            f"«{nickname}» está vinculado a una cuenta de Google: "
            "entra con el botón de Google."
        )
        return redirect(request.referrer or url_for("index"))
    repository.touch_user(nickname)
    session["nickname"] = nickname
    return redirect(request.referrer or url_for("index"))


def _derived_nickname(email: str) -> str:
    """A nickname from the email's local part, skipping ones another account owns."""
    base = (
        re.sub(r"[^a-z0-9_-]", "-", email.split("@")[0].lower())[:20].strip("-")
        or "user"
    )
    candidate = base
    for n in range(2, 100):
        user = repository.get_user(candidate)
        if not (user and user.get("google_email")):
            return candidate
        suffix = f"-{n}"
        candidate = base[: 20 - len(suffix)] + suffix
    return candidate


def google_login():
    """GIS login_uri target: Google's double-submit cookie replaces our
    session CSRF here (the POST is minted by the GIS script, which has no
    access to our form token)."""
    if not config.GOOGLE_CLIENT_ID:
        abort(404)
    if not helpers.LOGIN_LIMITER.allow(client_ip()):
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
    email = identity["email"]
    session["google_email"] = email
    session["google_name"] = identity["name"]
    # The Google account picks the nickname: the one it is linked to; else the
    # nickname already in the session, which it now claims; else a derived one.
    nickname = repository.find_nickname_by_google_email(email)
    linked = nickname is not None
    if not linked:
        current = session.get("nickname")
        current_user = repository.get_user(current) if current else None
        if current and not (current_user and current_user.get("google_email")):
            nickname = current
        else:
            nickname = _derived_nickname(email)
    user = repository.get_user(nickname)
    if user and user.get("blocked"):
        session.pop("nickname", None)
    else:
        if linked:
            repository.touch_user(nickname)
        else:
            repository.link_google_email(nickname, email)
        session["nickname"] = nickname
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
