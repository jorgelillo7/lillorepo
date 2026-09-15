"""Admin surface: users table, moderation and ficha repair (Google-verified
admins only)."""

from flask import abort, redirect, render_template, request, session, url_for

from core.web.csrf import verify_csrf_token
from packages.be_water.web import config, data_audit, geo, helpers, repository
from packages.be_water.web.submission import form_country, form_field, resolve_place


def admin_page():
    """Users table + moderation. Google-verified admin emails only; 404
    while Sign-In is unconfigured so the surface simply doesn't exist."""
    if not config.GOOGLE_CLIENT_ID:
        abort(404)
    if not helpers.is_admin():
        abort(403)
    users = repository.get_all_users()
    catalog = repository.get_all_waters()
    # `photo_promotion_failed` is set when a save could not move a photo out of
    # `uploads/`. That prefix is swept, so the ficha works for weeks and then
    # does not. Nothing read the flag, which made it an alarm with no bell.
    stranded = [w for w in catalog if w.photo_promotion_failed]
    # Origins a machine cannot repair: a wrong province is not something
    # re-reading the label fixes, so this is the page's human worklist.
    geo_gaps = data_audit.find_geo_gaps(catalog)
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
        stranded=stranded,
        geo_gaps=geo_gaps,
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


def _require_admin():
    """404 while Sign-In is unconfigured so the surface simply does not exist;
    403 for a visitor who is not an admin."""
    if not config.GOOGLE_CLIENT_ID:
        abort(404)
    if not helpers.is_admin():
        abort(403)


def admin_edit_water(water_id: str):
    """Repair a ficha's identity and origin.

    Deliberately not a mineral editor: `data_audit.correct_field` owns those,
    and they carry provenance this form has no way to ask about. What is here
    is what no machine can recover — where the bottle is from.

    Province, community and country are **selects** over the vocabularies this
    repo already carries. Free text is what let `province='portugal'` and the
    `tramuntana` field shift reach Firestore; a list cannot be mistyped.
    """
    _require_admin()
    water = repository.get_water(water_id)
    if water is None:
        abort(404)

    if request.method == "GET":
        return render_template(
            "admin_edit.html",
            water=water,
            reasons=data_audit.geo_reasons(water),
            provinces=geo.ALL_PROVINCES,
            communities=geo.ALL_COMMUNITIES,
            meta_description=f"Editar {water.name}.",
        )

    if not verify_csrf_token():
        abort(403)

    # Snapshot first: an admin edit is the one write with no contributor
    # behind it to ask what the label said, so it has to be undoable
    # (scripts/revert_water.py reads these).
    repository.save_revision(
        water,
        replaced_by=session.get("google_email", "admin"),
        reason="admin edit: identity and origin",
    )

    country = form_country(request.form)
    province, community = resolve_place(
        form_field(request.form, "province"),
        form_field(request.form, "community"),
        country,
    )
    water.name = form_field(request.form, "name") or water.name
    water.brand = form_field(request.form, "brand") or water.name
    water.spring = form_field(request.form, "spring")
    water.retailer = form_field(request.form, "retailer") or None
    water.country = country
    water.province = province
    water.community = community
    repository.save_water(water)
    return redirect(url_for("water_detail", water_id=water.id))


def register(app):
    app.add_url_rule("/admin", "admin_page", admin_page)
    app.add_url_rule(
        "/admin/agua/<water_id>",
        "admin_edit_water",
        admin_edit_water,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/admin/bloquear/<nickname>",
        "admin_toggle_block",
        admin_toggle_block,
        methods=["POST"],
    )
