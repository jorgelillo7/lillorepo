"""Public pages, favourites, and SEO/plumbing endpoints."""

from datetime import datetime, timezone
from urllib.parse import quote
from xml.sax.saxutils import escape

from flask import (
    Response,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from core.web.csrf import verify_csrf_token
from packages.be_water.web import (
    aesan,
    community,
    config,
    helpers,
    repository,
    seo,
    similarity,
)
from packages.be_water.web import domain
from packages.be_water.web.domain import format_mineral, mineralization_label


def index():
    catalog = sorted(repository.get_all_waters(), key=lambda w: w.name.lower())
    return render_template(
        "index.html",
        waters=catalog,
        places=helpers.places(catalog),
        favorite_ids=helpers.favorite_ids(),
        structured_data=seo.site(helpers.base_url()),
        og_image=seo.first_photo(catalog),
        meta_description=(
            "Catálogo abierto de aguas minerales españolas: composición, "
            "procedencia y aguas parecidas a la tuya estés donde estés."
        ),
    )


def water_detail(water_id: str):
    catalog = repository.get_all_waters()
    water = next((w for w in catalog if w.id == water_id), None)
    if water is None:
        abort(404)

    # The ficha shows the current composition; `?analisis=` swaps in a past
    # one. `similar` keeps reading `water`: what a water resembles is a
    # property of the water, not of one measurement of it, so a water with
    # four analyses is still one entry everywhere else. Everything that
    # describes *this page* follows `shown` — the canonical tag, which drops
    # `analisis`, is what consolidates the variants for a crawler.
    # An undated water cannot have a series — only dated compositions enter
    # one — so three quarters of the catalog skips the read entirely.
    analyses = repository.list_analyses(water_id) if water.analysis_date else []
    viewing = (request.args.get("analisis") or "").strip()
    shown = water
    if viewing and viewing != water.analysis_date:
        entry = next((a for a in analyses if a.get("analysis_date") == viewing), None)
        if entry is None:
            abort(404)
        shown = water.with_analysis(entry)

    similar = similarity.similar_waters(water, catalog, top_n=3)
    home = helpers.base_url()
    return render_template(
        "water.html",
        water=shown,
        analyses=analyses,
        viewing_past=shown is not water,
        current_analysis_date=water.analysis_date,
        similar=similar,
        mineral_scale=domain.mineral_scale(catalog),
        favorite_ids=helpers.favorite_ids(),
        og_image=shown.photo_url,
        structured_data=seo.water_page(
            shown,
            url=f"{home}/agua/{water.id}",
            home_url=home,
            place_url=f"{home}/recomendar?lugar={quote(water.province)}",
        ),
        meta_description=(
            f"{shown.name}{f' ({shown.province})' if shown.province else ''}: "
            f"residuo seco "
            f"{format_mineral(shown.tds) if shown.tds is not None else '?'} mg/L, "
            f"mineralización {shown.mineralization}. "
            "Composición completa y aguas similares."
        ),
    )


def recommend():
    """What to drink in a place. The listing is public: `lugar` decides the
    set, identity only decides the order."""
    catalog = repository.get_all_waters()
    place = (request.args.get("lugar") or "").strip()
    nickname = session.get("nickname")
    favorites = repository.get_favorites(nickname, catalog) if nickname else []
    # Personalised by default for anyone with favourites; `?perfil=0` opts out.
    # Written as an opt-out so a stray param in a shared URL degrades to the
    # neutral view instead of needing a case of its own.
    personalized = bool(favorites) and request.args.get("perfil") != "0"

    region = similarity.waters_in_place(catalog, place)
    fav_ids = {w.id for w in favorites}
    # The region keeps your favourites — "what do I drink here" is best
    # answered by your own water when it is from here. "What else is around"
    # is not, so nearby drops them.
    nearby = [
        w for w in similarity.waters_near_place(catalog, place) if w.id not in fav_ids
    ]

    if personalized:
        centroid = similarity.favorites_centroid(favorites)
        region = similarity.rank_by_centroid(region, centroid)
        nearby = similarity.rank_by_centroid(nearby, centroid)
    else:
        region = similarity.by_mineralization(region)
        nearby = similarity.by_mineralization(nearby)

    return render_template(
        "recommend.html",
        places=helpers.places(catalog),
        place=place,
        favorites=favorites,
        personalized=personalized,
        region=region,
        nearby=nearby,
        favorite_ids=fav_ids,
        page_title=(f"Aguas minerales de {place}" if place else "Estoy de viaje"),
        meta_description=_recommend_description(place, region, nearby),
        og_image=seo.first_photo(region, nearby),
        structured_data=(
            seo.place_page(
                place,
                region,
                url=f"{helpers.base_url()}/recomendar?lugar={quote(place)}",
                home_url=helpers.base_url(),
            )
            if place and region
            else None
        ),
    )


def _recommend_description(place: str, region: list, nearby: list) -> str:
    """Per-place meta description — these URLs are in the sitemap, and a set of
    pages sharing one description is a set of pages indexed as duplicates."""
    if not place:
        return (
            "Dinos dónde estás y te decimos qué aguas minerales hay en la "
            "zona, con su composición."
        )
    if len(region) == 1:
        return (
            f"{region[0].name}, el agua mineral de {place}: residuo seco, "
            "composición y aguas parecidas."
        )
    if region:
        return (
            f"Las {len(region)} aguas minerales de {place}: residuo seco, "
            "composición y cuál se parece más a tu gusto."
        )
    if nearby:
        return (
            f"No conocemos aguas embotelladas de {place}. Las "
            f"{len(nearby)} más cercanas, con su composición."
        )
    return f"Aguas minerales de {place} en el catálogo abierto de Be Water."


def community_page():
    """Public contributor ranking + achievements."""
    catalog = repository.get_all_waters()
    period = request.args.get("periodo", "siempre")
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    ranking = community.build_community_stats(
        catalog, month_prefix, repository.all_analyses()
    )
    if period == "mes":
        ranking = [s for s in ranking if s["month_score"] > 0]
        ranking.sort(key=lambda s: (-s["month_score"], s["nickname"]))
    catalog_names = [w.name for w in catalog] + [w.brand for w in catalog]
    return render_template(
        "community.html",
        ranking=ranking,
        period=period,
        catalog_size=len(catalog),
        aesan=aesan.coverage(catalog_names),
        pending=aesan.pending_waters(catalog_names),
        achievements=[
            {"emoji": emoji, "name": name, "description": description}
            for emoji, name, description, _ in community.ACHIEVEMENTS
        ],
        meta_description=(
            "La comunidad de Be Water: quién añade y verifica las aguas "
            "del catálogo."
        ),
    )


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


def profile():
    """Your water identity: what your favorites say about your taste."""
    nickname = session.get("nickname")
    catalog = repository.get_all_waters()
    favorites = repository.get_favorites(nickname, catalog) if nickname else []
    centroid = similarity.favorites_centroid(favorites)
    # Mean to match against, median to describe with — see `favorites_profile`.
    described = similarity.favorites_profile(favorites)
    traits = similarity.profile_traits(described, catalog) if described else []
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
    return render_template(
        "profile.html",
        favorites=favorites,
        favorite_ids={w.id for w in favorites},
        traits=traits,
        mineralization=(
            mineralization_label(centroid.get("tds")) if centroid else None
        ),
        spread=similarity.mineralization_spread(favorites),
        matches=matches,
        meta_description=(
            "Tu perfil de agua: qué composición te gusta y qué aguas encajan "
            "contigo."
        ),
    )


def favorite(water_id: str):
    if not verify_csrf_token():
        return redirect(request.referrer or url_for("water_detail", water_id=water_id))
    nickname = session.get("nickname")
    if nickname:
        repository.toggle_favorite(nickname, water_id)
        repository.touch_user(nickname)
    return redirect(request.referrer or url_for("water_detail", water_id=water_id))


def health():
    return {"status": "ok"}, 200


def version():
    return {
        "service": "be-water",
        "commit": config.GIT_COMMIT,
        "deploy_time": config.DEPLOY_TIME,
    }, 200


def robots():
    # The Sitemap line is how a crawler finds the file without being told:
    # /robots.txt is the one URL every crawler fetches unprompted.
    body = f"User-agent: *\nAllow: /\n\nSitemap: {helpers.base_url()}/sitemap.xml\n"
    return Response(body, mimetype="text/plain")


def sitemap():
    base = helpers.base_url()
    catalog = repository.get_all_waters()
    # (url, lastmod) — lastmod only where a real date exists. Inventing one
    # for every page on every request teaches a crawler to ignore the field.
    urls = [
        (f"{base}/", ""),
        (f"{base}/recomendar", ""),
        (f"{base}/comunidad", ""),
        (f"{base}/acerca", ""),
    ]
    urls += [(f"{base}/agua/{w.id}", (w.added_at or "")[:10]) for w in catalog]
    # Place pages serve real content to an anonymous crawler now, so they are
    # worth indexing. Only places the catalogue actually covers: a page whose
    # answer is "we know of none here" is not one to invite Google to.
    places = sorted({w.province for w in catalog} | {w.community for w in catalog})
    urls += [(f"{base}/recomendar?lugar={quote(p)}", "") for p in places if p]
    body = "".join(
        f"<url><loc>{escape(u)}</loc>"
        + (f"<lastmod>{escape(mod)}</lastmod>" if mod else "")
        + "</url>"
        for u, mod in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</urlset>"
    )
    return Response(xml, mimetype="application/xml")


def register(app):
    app.add_url_rule("/", "index", index)
    app.add_url_rule("/agua/<water_id>", "water_detail", water_detail)
    app.add_url_rule("/recomendar", "recommend", recommend)
    app.add_url_rule("/comunidad", "community_page", community_page)
    app.add_url_rule("/acerca", "about", about)
    app.add_url_rule("/perfil", "profile", profile)
    app.add_url_rule("/favorito/<water_id>", "favorite", favorite, methods=["POST"])
    app.add_url_rule("/health", "health", health)
    app.add_url_rule("/version", "version", version)
    app.add_url_rule("/robots.txt", "robots", robots)
    app.add_url_rule("/sitemap.xml", "sitemap", sitemap)
