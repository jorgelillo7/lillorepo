"""Be Water — compare Spanish bottled waters and find yours anywhere."""

import os
import re
import uuid

import requests
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

from core.sdk.gemini import GeminiError
from core.utils import get_logger
from packages.be_water.web import config, label_ocr, photos, repository, similarity
from packages.be_water.web.domain import MINERAL_FIELDS, MINERAL_LABELS, Water

logger = get_logger(__name__)

_NICKNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{2,20}$")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

template_dir = os.path.join(os.path.dirname(__file__), "templates")
app = Flask(__name__, template_folder=template_dir)
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower() != "false",
)


@app.context_processor
def inject_globals() -> dict:
    return {
        "nickname": session.get("nickname"),
        "git_commit": config.GIT_COMMIT,
        "mineral_labels": MINERAL_LABELS,
        "mineral_fields": MINERAL_FIELDS,
    }


def _places(catalog: list[Water]) -> list[str]:
    """Distinct provinces + communities, for the '¿dónde estás?' selector."""
    places = {w.province for w in catalog} | {w.community for w in catalog}
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
    return render_template(
        "recommend.html",
        places=_places(catalog),
        place=place,
        favorites=favorites,
        results=results,
        favorite_ids={w.id for w in favorites},
        meta_description=(
            "Dinos dónde estás y te recomendamos aguas de la zona parecidas "
            "a tus favoritas."
        ),
    )


@app.route("/anadir", methods=["GET", "POST"])
def add_water():
    if not session.get("nickname"):
        return redirect(url_for("index"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            abort(400)
        water_id = _SLUG_RE.sub("-", name.lower()).strip("-")
        if repository.get_water(water_id) is not None:
            # Never clobber an existing (possibly verified) water from the form.
            return _render_add_form(
                prefill=dict(request.form),
                photo_tmp=request.form.get("photo_tmp") or None,
                error=f"«{name}» ya existe en el catálogo — edítala desde su ficha.",
            )
        minerals = {}
        for field in MINERAL_FIELDS:
            raw = (request.form.get(field) or "").strip().replace(",", ".")
            if raw:
                try:
                    minerals[field] = float(raw)
                except ValueError:
                    pass
        photo_url = None
        photo_tmp = (request.form.get("photo_tmp") or "").strip()
        if photo_tmp:
            try:
                photo_url = photos.promote_photo(photo_tmp, f"{water_id}.jpg")
            except requests.RequestException:
                photo_url = photos.public_url(photo_tmp)  # keep tmp as fallback
        water = Water(
            id=water_id,
            name=name,
            brand=(request.form.get("brand") or name).strip(),
            spring=(request.form.get("spring") or "").strip(),
            province=(request.form.get("province") or "").strip(),
            community=(request.form.get("community") or "").strip(),
            sparkling=request.form.get("sparkling") == "on",
            minerals=minerals,
            photo_url=photo_url,
            added_by=session["nickname"],
        )
        repository.save_water(water)
        return redirect(url_for("water_detail", water_id=water_id))
    return _render_add_form()


@app.route("/anadir/foto", methods=["POST"])
def add_water_photo():
    """Photo-first flow: upload the label shot, let Gemini pre-fill the form."""
    if not session.get("nickname"):
        return redirect(url_for("index"))
    upload = request.files.get("photo")
    if upload is None or not upload.filename:
        return redirect(url_for("add_water"))
    raw = upload.read(photos.MAX_UPLOAD_BYTES + 1)
    if len(raw) > photos.MAX_UPLOAD_BYTES:
        return _render_add_form(error="La foto es demasiado grande (máx. 15 MB).")

    processed = photos.process_image(raw)
    tmp_name = f"uploads/{uuid.uuid4().hex}.jpg"
    photos.upload_photo(tmp_name, processed)

    try:
        extracted = label_ocr.extract_label(processed)
    except (GeminiError, requests.RequestException) as exc:
        logger.warning("Label OCR failed.", extra={"error": str(exc)[:300]})
        # OCR down ≠ photo lost: open the empty form with the photo attached.
        return _render_add_form(
            photo_tmp=tmp_name,
            error="No pude leer la etiqueta automáticamente — rellena a mano.",
        )
    prefill = {k: v for k, v in extracted.items() if v is not None}
    return _render_add_form(
        prefill=prefill,
        photo_tmp=tmp_name,
        notice="He leído la etiqueta — revisa los valores antes de guardar.",
    )


def _render_add_form(prefill=None, photo_tmp=None, error=None, notice=None):
    return render_template(
        "add.html",
        prefill=prefill or {},
        photo_tmp=photo_tmp,
        photo_tmp_url=photos.public_url(photo_tmp) if photo_tmp else None,
        error=error,
        notice=notice,
        meta_description="Añade una nueva agua al catálogo con su etiqueta.",
    )


# --- Session ----------------------------------------------------------------


@app.route("/login", methods=["POST"])
def login():
    nickname = (request.form.get("nickname") or "").strip().lower()
    if not _NICKNAME_RE.match(nickname):
        return redirect(request.referrer or url_for("index"))
    repository.ensure_user(nickname)
    session["nickname"] = nickname
    return redirect(request.referrer or url_for("index"))


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("nickname", None)
    return redirect(url_for("index"))


@app.route("/favorito/<water_id>", methods=["POST"])
def favorite(water_id: str):
    nickname = session.get("nickname")
    if nickname:
        repository.toggle_favorite(nickname, water_id)
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
    urls = [f"{base}/", f"{base}/recomendar"]
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
