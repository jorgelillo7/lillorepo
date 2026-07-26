"""Admin surface: users table + moderation (Google-verified admins only)."""

from flask import abort, redirect, render_template, url_for

from core.web.csrf import verify_csrf_token
from packages.be_water.web import config, helpers, repository


def admin_page():
    """Users table + moderation. Google-verified admin emails only; 404
    while Sign-In is unconfigured so the surface simply doesn't exist."""
    if not config.GOOGLE_CLIENT_ID:
        abort(404)
    if not helpers.is_admin():
        abort(403)
    users = repository.get_all_users()
    catalog = repository.get_all_waters()
    contributions: dict = {}
    for water in catalog:
        contributor = (water.added_by or "").strip().lower()
        if contributor and contributor != "seed":
            contributions[contributor] = contributions.get(contributor, 0) + 1
    rows = [
        {
            "nickname": nickname,
            "created_at": (data.get("created_at") or "")[:10],
            "last_seen": (data.get("last_seen") or "")[:10],
            "favorites": len(data.get("favorites", [])),
            "waters": contributions.get(nickname, 0),
            "blocked": bool(data.get("blocked")),
        }
        for nickname, data in sorted(users.items())
    ]
    return render_template(
        "admin.html",
        rows=rows,
        admin_emails=sorted(config.ADMIN_EMAILS),
        meta_description="Administración de Be Water.",
    )


def admin_toggle_block(nickname: str):
    if not config.GOOGLE_CLIENT_ID:
        abort(404)
    if not helpers.is_admin() or not verify_csrf_token():
        abort(403)
    user = repository.get_user(nickname)
    if user is None:
        abort(404)
    repository.set_user_blocked(nickname, not user.get("blocked"))
    return redirect(url_for("admin_page"))


def register(app):
    app.add_url_rule("/admin", "admin_page", admin_page)
    app.add_url_rule(
        "/admin/bloquear/<nickname>",
        "admin_toggle_block",
        admin_toggle_block,
        methods=["POST"],
    )
