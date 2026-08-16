"""Shared request helpers, rate limiters and template globals for the be_water
routes. Kept app-free (no Flask app import) so the `routes/` modules can share
them without a circular import."""

import re

from flask import request, session

from core.web.csrf import get_csrf_token
from core.web.ratelimit import RateLimiter
from packages.be_water.web import config, geo, repository
from packages.be_water.web.domain import (
    MINERAL_FIELDS,
    MINERAL_FIELDS_EXTRA,
    MINERAL_FIELDS_MAIN,
    MINERAL_LABELS,
    Water,
)

NICKNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{2,20}$")

# Abuse basics for the public phase: per-instance sliding windows keyed by
# client IP. The photo limit doubles as a spend cap on the Gemini calls.
LOGIN_LIMITER = RateLimiter(20, 300)
SAVE_LIMITER = RateLimiter(30, 3600)
PHOTO_LIMITER = RateLimiter(15, 3600)


def is_admin() -> bool:
    return (session.get("google_email") or "") in config.ADMIN_EMAILS


def nickname_blocked() -> bool:
    user = repository.get_user(session.get("nickname", ""))
    return bool(user and user.get("blocked"))


def client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr or "?"


def places(catalog: list[Water]) -> list[str]:
    """Every province and every community, for the '¿dónde estás?' selector.

    The full geography, not the part the catalogue happens to mention: a place
    with no water of its own answers with its neighbours', and one with
    neither invites you to add the first. Listing only the covered communities
    hid Comunidad de Madrid, Región de Murcia and Canarias from the selector.
    """
    names = {w.province for w in catalog} | {w.community for w in catalog}
    names |= set(geo.ALL_PROVINCES) | set(geo.ALL_COMMUNITIES)
    return sorted(p for p in names if p)


def favorite_ids() -> set[str]:
    nickname = session.get("nickname")
    if not nickname:
        return set()
    user = repository.get_user(nickname)
    return set(user.get("favorites", [])) if user else set()


def context_data() -> dict:
    """Template globals injected on every render (registered as a context
    processor by `app.py`)."""
    return {
        "nickname": session.get("nickname"),
        "google_email": session.get("google_email"),
        "google_client_id": config.GOOGLE_CLIENT_ID,
        "is_admin": is_admin(),
        "git_commit": config.GIT_COMMIT,
        "mineral_labels": MINERAL_LABELS,
        "mineral_fields": MINERAL_FIELDS,
        "mineral_fields_main": MINERAL_FIELDS_MAIN,
        "mineral_fields_extra": MINERAL_FIELDS_EXTRA,
        "csrf_token": get_csrf_token,
    }
