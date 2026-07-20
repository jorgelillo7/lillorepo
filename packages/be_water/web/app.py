"""Be Water — compare Spanish bottled waters and find yours anywhere."""

import os
import re
import uuid
from typing import Optional

import requests
from unidecode import unidecode
from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from datetime import datetime, timezone

from core.sdk.gemini import GeminiError
from core.utils import get_logger
from core.web.csrf import get_csrf_token, verify_csrf_token
from core.web.ratelimit import RateLimiter
from packages.be_water.web import (
    aesan,
    auth,
    community,
    config,
    geo,
    label_ocr,
    photos,
    repository,
    similarity,
)
from packages.be_water.web.domain import (
    MINERAL_FIELDS,
    MINERAL_FIELDS_EXTRA,
    MINERAL_FIELDS_MAIN,
    MINERAL_LABELS,
    Water,
)

logger = get_logger(__name__)

_NICKNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{2,20}$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Abuse basics for the public phase: per-instance sliding windows keyed by
# client IP. The photo limit doubles as a spend cap on the Gemini calls.
_LOGIN_LIMITER = RateLimiter(20, 300)
_SAVE_LIMITER = RateLimiter(30, 3600)
_PHOTO_LIMITER = RateLimiter(15, 3600)
_MAX_FIELD_LEN = 80
_MAX_MINERAL_VALUE = 100_000  # mg/L — beyond this it's not water

template_dir = os.path.join(os.path.dirname(__file__), "templates")
app = Flask(__name__, template_folder=template_dir)
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false",
)


def _is_admin() -> bool:
    return (session.get("google_email") or "") in config.ADMIN_EMAILS


def _nickname_blocked() -> bool:
    user = repository.get_user(session.get("nickname", ""))
    return bool(user and user.get("blocked"))


@app.context_processor
def inject_globals() -> dict:
    return {
        "nickname": session.get("nickname"),
        "google_email": session.get("google_email"),
        "google_client_id": config.GOOGLE_CLIENT_ID,
        "is_admin": _is_admin(),
        "git_commit": config.GIT_COMMIT,
        "mineral_labels": MINERAL_LABELS,
        "mineral_fields": MINERAL_FIELDS,
        "mineral_fields_main": MINERAL_FIELDS_MAIN,
        "mineral_fields_extra": MINERAL_FIELDS_EXTRA,
        "csrf_token": get_csrf_token,
    }


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr or "?"


def _form_field(name: str) -> str:
    """Trimmed form value, length-capped — nobody's manantial needs 80+ chars."""
    return (request.form.get(name) or "").strip()[:_MAX_FIELD_LEN]


def _springs_differ(submitted: str, current: str) -> bool:
    """True when both springs are declared and neither's token set contains
    the other's — i.e. genuinely different sources, not spelling drift."""
    a = set(_SLUG_RE.sub(" ", unidecode(submitted).lower()).split())
    b = set(_SLUG_RE.sub(" ", unidecode(current).lower()).split())
    return bool(a) and bool(b) and not (a <= b or b <= a)


def _similar_water(name: str, catalog: list[Water]) -> Optional[Water]:
    """Fuzzy duplicate guard: token-subset match on normalized names, so
    "Naturis" flags «Naturis (Lidl) — Albacete». Exact slugs are handled
    upstream; near-misses come back for the user to decide — white labels
    bottled from several springs are legitimately several waters."""
    tokens = set(_SLUG_RE.sub(" ", unidecode(name).lower()).split())
    if not tokens:
        return None
    for water in catalog:
        for candidate in (water.name, water.brand):
            cand = set(_SLUG_RE.sub(" ", unidecode(candidate).lower()).split())
            if cand and (tokens <= cand or cand <= tokens):
                return water
    return None


def _places(catalog: list[Water]) -> list[str]:
    """Every province plus the catalog's communities, for the '¿dónde
    estás?' selector — provinces without waters resolve via the
    nearby-province fallback."""
    places = {w.province for w in catalog} | {w.community for w in catalog}
    places |= set(geo.ALL_PROVINCES)
    return sorted(p for p in places if p)


def _favorite_ids() -> set[str]:
    nickname = session.get("nickname")
    if not nickname:
        return set()
    user = repository.get_user(nickname)
    return set(user.get("favorites", [])) if user else set()


# --- Pages -----------------------------------------------------------------


@app.route("/")
def index():
    catalog = sorted(repository.get_all_waters(), key=lambda w: w.name.lower())
    return render_template(
        "index.html",
        waters=catalog,
        places=_places(catalog),
        favorite_ids=_favorite_ids(),
        meta_description=(
            "Catálogo abierto de aguas minerales españolas: composición, "
            "procedencia y aguas parecidas a la tuya estés donde estés."
        ),
    )


@app.route("/agua/<water_id>")
def water_detail(water_id: str):
    catalog = repository.get_all_waters()
    water = next((w for w in catalog if w.id == water_id), None)
    if water is None:
        abort(404)
    similar = similarity.similar_waters(water, catalog, top_n=3)
    return render_template(
        "water.html",
        water=water,
        similar=similar,
        favorite_ids=_favorite_ids(),
        meta_description=(
            f"{water.name} ({water.province}): residuo seco "
            f"{water.tds or '?'} mg/L, mineralización {water.mineralization}. "
            "Composición completa y aguas similares."
        ),
    )


@app.route("/recomendar")
def recommend():
    catalog = repository.get_all_waters()
    place = (request.args.get("lugar") or "").strip()
    nickname = session.get("nickname")
    favorites = repository.get_favorites(nickname, catalog) if nickname else []
    results = (
        similarity.recommend(favorites, catalog, place) if place and favorites else []
    )
    nearby = (
        similarity.recommend_nearby(favorites, catalog, place)
        if place and favorites and not results
        else []
    )
    return render_template(
        "recommend.html",
        places=_places(catalog),
        place=place,
        favorites=favorites,
        results=results,
        nearby=nearby,
        favorite_ids={w.id for w in favorites},
        meta_description=(
            "Dinos dónde estás y te recomendamos aguas de la zona parecidas "
            "a tus favoritas."
        ),
    )


@app.route("/comunidad")
def community_page():
    """Public contributor ranking + achievements."""
    catalog = repository.get_all_waters()
    period = request.args.get("periodo", "siempre")
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    ranking = community.build_community_stats(catalog, month_prefix)
    if period == "mes":
        ranking = [s for s in ranking if s["month_score"] > 0]
        ranking.sort(key=lambda s: (-s["month_score"], s["nickname"]))
    catalog_names = [w.name for w in catalog] + [w.brand for w in catalog]
    return render_template(
        "community.html",
        ranking=ranking,
        period=period,
        aesan=aesan.coverage(catalog_names),
        achievements=[
            {"emoji": emoji, "name": name, "description": description}
            for emoji, name, description, _ in community.ACHIEVEMENTS
        ],
        meta_description=(
            "La comunidad de Be Water: quién añade y verifica las aguas "
            "del catálogo."
        ),
    )


@app.route("/acerca")
def about():
    catalog = repository.get_all_waters()
    catalog_names = [w.name for w in catalog] + [w.brand for w in catalog]
    return render_template(
        "about.html",
        catalog_size=len(catalog),
        aesan=aesan.coverage(catalog_names),
        meta_description=(
            "Qué es Be Water, de dónde salen los datos del catálogo y cómo "
            "se verifican las composiciones."
        ),
    )


@app.route("/perfil")
def profile():
    """Your water identity: what your favorites say about your taste."""
    nickname = session.get("nickname")
    catalog = repository.get_all_waters()
    favorites = repository.get_favorites(nickname, catalog) if nickname else []
    centroid = similarity.favorites_centroid(favorites)
    traits = similarity.profile_traits(centroid, catalog) if centroid else []
    matches = []
    if centroid:
        fav_ids = {w.id for w in favorites}
        scored = [
            (w, similarity.distance(centroid, w.minerals))
            for w in catalog
            if w.id not in fav_ids
        ]
        scored = [(w, d) for w, d in scored if d != float("inf")]
        scored.sort(key=lambda t: t[1])
        matches = scored[:6]
    from packages.be_water.web.domain import mineralization_label

    return render_template(
        "profile.html",
        favorites=favorites,
        favorite_ids={w.id for w in favorites},
        traits=traits,
        mineralization=(
            mineralization_label(centroid.get("tds")) if centroid else None
        ),
        matches=matches,
        meta_description=(
            "Tu perfil de agua: qué composición te gusta y qué aguas encajan "
            "contigo."
        ),
    )


@app.route("/anadir", methods=["GET", "POST"])
def add_water():
    if not session.get("nickname"):
        return redirect(url_for("index"))
    if request.method == "POST":
        if _nickname_blocked():
            return redirect(url_for("index"))
        if not verify_csrf_token():
            return _render_add_form(
                prefill=dict(request.form),
                error="La sesión ha caducado — recarga la página e inténtalo de nuevo.",
            )
        if not _SAVE_LIMITER.allow(_client_ip()):
            return _render_add_form(
                prefill=dict(request.form),
                error="Demasiadas aguas en poco tiempo — espera un rato.",
            )
        name = _form_field("name")
        if not name:
            abort(400)
        # unidecode first: "Lanjarón" must slug to "lanjaron", not "lanjar-n",
        # or the duplicate guard misses the existing doc (real bug, 2nd day live).
        water_id = _SLUG_RE.sub("-", unidecode(name).lower()).strip("-")
        existing = repository.get_water(water_id)
        merge_into = (request.form.get("merge_into") or "").strip()
        if existing is None and merge_into:
            # The user confirmed the fuzzy match: update that water instead.
            existing = repository.get_water(merge_into)
            if existing is None:
                abort(400)
            water_id = merge_into
        elif existing is None and not request.form.get("force_new"):
            similar = _similar_water(name, repository.get_all_waters())
            if similar is not None:
                return _render_add_form(
                    prefill=dict(request.form),
                    photo_tmp=request.form.get("photo_tmp") or None,
                    label_tmp=request.form.get("label_tmp") or None,
                    ocr_fields=request.form.get("ocr_fields") or None,
                    similar=similar,
                )
        if (
            existing is not None
            and not merge_into
            and not request.form.get("force_new")
            and _springs_differ(_form_field("spring"), existing.spring)
        ):
            # Exact commercial name, different spring — the Font Vella case
            # (Sacalm vs Sigüenza): ask instead of silently merging.
            return _render_add_form(
                prefill=dict(request.form),
                photo_tmp=request.form.get("photo_tmp") or None,
                label_tmp=request.form.get("label_tmp") or None,
                ocr_fields=request.form.get("ocr_fields") or None,
                similar=existing,
            )
        if existing is not None and request.form.get("force_new"):
            # A new water sharing the exact name: id disambiguated by the
            # spring tokens the name doesn't already carry.
            spring_tokens = _SLUG_RE.sub(
                " ", unidecode(_form_field("spring")).lower()
            ).split()
            extra = [t for t in spring_tokens if t not in water_id]
            if extra:
                water_id = f"{water_id}-{'-'.join(extra)}"
                existing = repository.get_water(water_id)
        if existing is not None and existing.verified:
            # A verified water is bottle-checked and data-frozen.
            return _render_add_form(
                prefill=dict(request.form),
                photo_tmp=request.form.get("photo_tmp") or None,
                error=(
                    f"«{name}» ya está en el catálogo y verificada — "
                    "no se puede sobrescribir."
                ),
            )
        minerals = {}
        for field in MINERAL_FIELDS:
            raw = (request.form.get(field) or "").strip().replace(",", ".")
            if raw:
                try:
                    value = float(raw)
                except ValueError:
                    continue
                if 0 <= value <= _MAX_MINERAL_VALUE:
                    minerals[field] = value
        photo_url = None
        label_photo_url = None
        photo_tmp = (request.form.get("photo_tmp") or "").strip()
        label_tmp = (request.form.get("label_tmp") or "").strip()
        if photo_tmp:
            try:
                photo_url = photos.promote_photo(photo_tmp, f"{water_id}.jpg")
            except requests.RequestException:
                photo_url = photos.public_url(photo_tmp)  # keep tmp as fallback
        if label_tmp:
            try:
                label_photo_url = photos.promote_photo(
                    label_tmp, f"originals/{water_id}.jpg"
                )
            except requests.RequestException:
                label_photo_url = photos.public_url(label_tmp)
        ocr_fields = (request.form.get("ocr_fields") or "").split(",")
        verified_fields = sorted(f for f in ocr_fields if f in minerals)
        water = Water(
            id=water_id,
            name=name,
            brand=_form_field("brand") or name,
            spring=_form_field("spring"),
            province=_form_field("province"),
            community=_form_field("community"),
            sparkling=request.form.get("sparkling") == "on",
            minerals=minerals,
            photo_url=photo_url,
            label_photo_url=label_photo_url,
            verified_fields=verified_fields,
            added_by=session["nickname"],
            added_at=datetime.now(timezone.utc).isoformat(),
        )
        if existing is not None:
            # Label-backed update of an unverified water: the reviewed form
            # wins, everything it can't carry survives from the current doc.
            if merge_into:
                # Confirmed fuzzy match: the canonical display name stays.
                water.name = existing.name
                water.retailer = existing.retailer
            water.minerals = {**existing.minerals, **water.minerals}
            water.sparkling = water.sparkling or existing.sparkling
            water.spring = water.spring or existing.spring
            water.province = water.province or existing.province
            water.community = water.community or existing.community
            if not _form_field("brand"):
                water.brand = existing.brand or water.brand
            water.photo_url = water.photo_url or existing.photo_url
            water.label_photo_url = water.label_photo_url or existing.label_photo_url
            water.mentions = existing.mentions
            water.verified_fields = sorted(
                set(water.verified_fields) | set(existing.verified_fields)
            )
            # Seeded waters get adopted by whoever backs them with a label;
            # a real user's water keeps its original author.
            if existing.added_by and existing.added_by != "seed":
                water.added_by = existing.added_by
                water.added_at = existing.added_at
        # Auto-promotion: label proof on file and every declared mineral
        # backed by it → the whole ficha is verified (and data-frozen
        # against the monthly dataset sync).
        if (
            water.label_photo_url
            and water.minerals
            and set(water.minerals) <= set(water.verified_fields)
        ):
            water.verified = True
        repository.save_water(water)
        repository.touch_user(session["nickname"])
        return redirect(url_for("water_detail", water_id=water_id))
    return _render_add_form()


@app.route("/anadir/foto", methods=["POST"])
def add_water_photo():
    """Photo-first flow: the composition shot feeds the OCR and stays as
    verification proof; an optional front shot becomes the display photo."""
    if not session.get("nickname") or _nickname_blocked():
        return redirect(url_for("index"))
    if not verify_csrf_token():
        return _render_add_form(
            error="La sesión ha caducado — recarga la página e inténtalo de nuevo."
        )
    if not _PHOTO_LIMITER.allow(_client_ip()):
        return _render_add_form(
            error="Demasiadas fotos en poco tiempo — espera un rato."
        )
    upload = request.files.get("photo")
    if upload is None or not upload.filename:
        return redirect(url_for("add_water"))
    raw = upload.read(photos.MAX_UPLOAD_BYTES + 1)
    if len(raw) > photos.MAX_UPLOAD_BYTES:
        return _render_add_form(error="La foto es demasiado grande (máx. 15 MB).")

    processed = photos.process_image(raw)
    uid = uuid.uuid4().hex
    # Both tmps live under uploads/ so the bucket lifecycle rule reclaims
    # abandoned forms; on save the label shot is promoted to originals/
    # as the permanent verification proof.
    label_tmp = f"uploads/{uid}-label.jpg"
    photos.upload_photo(label_tmp, processed)

    # The display photo prefers the optional front shot — a composition
    # label is usually the ugly side of the bottle.
    display_src = processed
    beauty = request.files.get("beauty")
    if beauty is not None and beauty.filename:
        beauty_raw = beauty.read(photos.MAX_UPLOAD_BYTES + 1)
        if len(beauty_raw) > photos.MAX_UPLOAD_BYTES:
            return _render_add_form(
                error="La foto de la ficha es demasiado grande (máx. 15 MB)."
            )
        display_src = photos.process_image(beauty_raw)

    # Studio version for display — admin-only: image generation is the one
    # paid call in the project, so it fires only for trusted nicknames.
    # Everyone else keeps the (free) OCR prefill and their raw photo.
    display = display_src
    studio_note = ""
    if session["nickname"] in config.ADMIN_NICKNAMES:
        try:
            display = photos.studio_photo(display_src)
            studio_note = " La foto ha pasado por el estudio 📸"
        except (GeminiError, requests.RequestException) as exc:
            logger.warning(
                "Studio photo failed — using raw.", extra={"error": str(exc)[:300]}
            )
    photo_tmp = f"uploads/{uid}.jpg"
    photos.upload_photo(photo_tmp, display)

    try:
        extracted = label_ocr.extract_label(processed)
    except (GeminiError, requests.RequestException) as exc:
        logger.warning("Label OCR failed.", extra={"error": str(exc)[:300]})
        # OCR down ≠ photo lost: open the empty form with the photo attached.
        overloaded = getattr(exc, "status_code", None) in (429, 503)
        error = (
            "El lector de etiquetas está saturado ahora mismo — "
            "prueba de nuevo en unos minutos, o rellena a mano."
            if overloaded
            else "No pude leer la etiqueta automáticamente — rellena a mano."
        )
        return _render_add_form(
            photo_tmp=photo_tmp,
            label_tmp=label_tmp,
            error=error,
        )
    prefill = {k: v for k, v in extracted.items() if v is not None}
    aesan_note = _prefill_from_aesan(prefill)
    # Mineral fields the label actually declared — they become
    # verified_fields on save (human-reviewed label data).
    ocr_fields = [f for f in MINERAL_FIELDS if prefill.get(f) is not None]
    return _render_add_form(
        prefill=prefill,
        photo_tmp=photo_tmp,
        label_tmp=label_tmp,
        ocr_fields=",".join(ocr_fields),
        notice="He leído la etiqueta — revisa los valores antes de guardar."
        + studio_note
        + aesan_note,
    )


def _prefill_from_aesan(prefill: dict) -> str:
    """Fill spring/province/community gaps from the official registry.

    The label always wins (only missing keys are filled); with several
    registry springs for the name, only fields all candidates agree on
    are used. Returns the notice suffix ('' when nothing matched)."""
    matches = aesan.registry_matches(prefill.get("name") or "")
    if not matches:
        return ""
    filled = False
    springs = {m["spring"] for m in matches}
    if len(springs) == 1 and not prefill.get("spring"):
        prefill["spring"] = springs.pop()
        filled = True
    provinces = {m["province"] for m in matches}
    if len(provinces) == 1:
        province = provinces.pop()
        if not prefill.get("province"):
            prefill["province"] = province
            filled = True
        if not prefill.get("community") and geo.community_of(province):
            prefill["community"] = geo.community_of(province)
            filled = True
    return " Procedencia completada del registro AESAN 📋" if filled else ""


def _render_add_form(
    prefill=None,
    photo_tmp=None,
    label_tmp=None,
    ocr_fields=None,
    error=None,
    notice=None,
    similar=None,
):
    return render_template(
        "add.html",
        prefill=prefill or {},
        photo_tmp=photo_tmp,
        label_tmp=label_tmp,
        ocr_fields=ocr_fields,
        photo_tmp_url=photos.public_url(photo_tmp) if photo_tmp else None,
        error=error,
        notice=notice,
        similar=similar,
        meta_description="Añade una nueva agua al catálogo con su etiqueta.",
    )


# --- Session ----------------------------------------------------------------


@app.route("/login", methods=["POST"])
def login():
    if not verify_csrf_token() or not _LOGIN_LIMITER.allow(_client_ip()):
        return redirect(request.referrer or url_for("index"))
    nickname = (request.form.get("nickname") or "").strip().lower()
    if not _NICKNAME_RE.match(nickname):
        return redirect(request.referrer or url_for("index"))
    user = repository.get_user(nickname)
    if user and user.get("blocked"):
        return redirect(request.referrer or url_for("index"))
    repository.touch_user(nickname)
    session["nickname"] = nickname
    return redirect(request.referrer or url_for("index"))


@app.route("/auth/google", methods=["POST"])
def google_login():
    """GIS login_uri target: Google's double-submit cookie replaces our
    session CSRF here (the POST is minted by the GIS script, which has no
    access to our form token)."""
    if not config.GOOGLE_CLIENT_ID:
        abort(404)
    if not _LOGIN_LIMITER.allow(_client_ip()):
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
    return redirect(url_for("admin_page") if _is_admin() else url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    if verify_csrf_token():
        session.pop("nickname", None)
        session.pop("google_email", None)
        session.pop("google_name", None)
    return redirect(url_for("index"))


# --- Admin -------------------------------------------------------------------


@app.route("/admin")
def admin_page():
    """Users table + moderation. Google-verified admin emails only; 404
    while Sign-In is unconfigured so the surface simply doesn't exist."""
    if not config.GOOGLE_CLIENT_ID:
        abort(404)
    if not _is_admin():
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


@app.route("/admin/bloquear/<nickname>", methods=["POST"])
def admin_toggle_block(nickname: str):
    if not config.GOOGLE_CLIENT_ID:
        abort(404)
    if not _is_admin() or not verify_csrf_token():
        abort(403)
    user = repository.get_user(nickname)
    if user is None:
        abort(404)
    repository.set_user_blocked(nickname, not user.get("blocked"))
    return redirect(url_for("admin_page"))


@app.route("/favorito/<water_id>", methods=["POST"])
def favorite(water_id: str):
    if not verify_csrf_token():
        return redirect(request.referrer or url_for("water_detail", water_id=water_id))
    nickname = session.get("nickname")
    if nickname:
        repository.toggle_favorite(nickname, water_id)
        repository.touch_user(nickname)
    return redirect(request.referrer or url_for("water_detail", water_id=water_id))


# --- Plumbing / SEO ----------------------------------------------------------


@app.route("/health")
def health():
    return {"status": "ok"}, 200


@app.route("/version")
def version():
    return {
        "service": "be-water",
        "commit": config.GIT_COMMIT,
        "deploy_time": config.DEPLOY_TIME,
    }, 200


@app.route("/robots.txt")
def robots():
    return Response("User-agent: *\nAllow: /\n", mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    base = config.BASE_URL or request.url_root.rstrip("/")
    urls = [f"{base}/", f"{base}/recomendar", f"{base}/comunidad", f"{base}/acerca"]
    urls += [f"{base}/agua/{w.id}" for w in repository.get_all_waters()]
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</urlset>"
    )
    return Response(xml, mimetype="application/xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)
