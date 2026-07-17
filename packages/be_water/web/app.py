"""Be Water — compare Spanish bottled waters and find yours anywhere."""

import os
import re

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

from packages.be_water.web import config, repository, similarity
from packages.be_water.web.domain import MINERAL_FIELDS, MINERAL_LABELS, Water

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
        minerals = {}
        for field in MINERAL_FIELDS:
            raw = (request.form.get(field) or "").strip().replace(",", ".")
            if raw:
                try:
                    minerals[field] = float(raw)
                except ValueError:
                    pass
        water = Water(
            id=water_id,
            name=name,
            brand=(request.form.get("brand") or name).strip(),
            spring=(request.form.get("spring") or "").strip(),
            province=(request.form.get("province") or "").strip(),
            community=(request.form.get("community") or "").strip(),
            sparkling=request.form.get("sparkling") == "on",
            minerals=minerals,
            added_by=session["nickname"],
        )
        repository.save_water(water)
        return redirect(url_for("water_detail", water_id=water_id))
    return render_template(
        "add.html",
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
