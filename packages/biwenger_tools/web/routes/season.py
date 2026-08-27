"""Season-scoped routes: comunicados, salseo, participacion, mercado,
lloros_awards, and their API endpoints.

Data flow:
- Content (comunicados/datos/cronicas/clausulazos/participacion/tabla)
  comes from Firestore via `repository.*`. Filtering, ordering, and
  pagination all happen server-side — see the inline queries there.
- The awards page (Liga H2H + trofeos) comes from Google Sheets —
  hand-edited by the league, not part of the Firestore data set. H2H is
  server-rendered because it is what people open the page for; trofeos
  loads on demand.
"""

import time
from dataclasses import asdict

import requests

from flask import Blueprint, Response, g, jsonify, render_template, request

from core.sdk.gcp import get_sheet_rows, get_sheets_data
from core.utils import get_logger
from packages.biwenger_tools.web import config, h2h as h2h_logic, repository, services
from packages.biwenger_tools.web.sanitize import safe_html, to_text

logger = get_logger(__name__)
bp = Blueprint("season", __name__)


def _sanitize_contenido(messages: list) -> list:
    """Pre-render `contenido` as HTML-escaped Markup with <br> for newlines.

    Templates either render it via the `safe_html` Jinja filter or ship it
    to JS via `tojson` for `innerHTML`; doing the sanitization on read makes
    both paths XSS-safe regardless of what Biwenger writes upstream.
    """
    for m in messages:
        m.contenido = str(safe_html(m.contenido))
    return messages


# --- Content routes (Firestore) ------------------------------------------


@bp.route("/<season>/")
def comunicados(season: str) -> str:
    """Display paginated announcements for a given season — newest first.

    Reads cost ~1 (count aggregation) + N (page size) per request, no
    matter how many comunicados live in the season.
    """
    error = None
    paginated_messages: list = []
    page = 1
    total_pages = 1
    try:
        page = max(1, request.args.get("page", 1, type=int))
        offset = (page - 1) * config.MESSAGES_PER_PAGE
        total = repository.count_messages_by_category(season, "comunicado")
        total_pages = max(
            1,
            (total + config.MESSAGES_PER_PAGE - 1) // config.MESSAGES_PER_PAGE,
        )
        paginated_messages = _sanitize_contenido(
            repository.get_messages_by_category(
                season,
                "comunicado",
                limit=config.MESSAGES_PER_PAGE,
                offset=offset,
            )
        )
    except Exception:
        error = f"Ocurrió un error al cargar los comunicados de la temporada {season}."
        logger.exception(
            "Error loading comunicados from Firestore.", extra={"season": season}
        )
    return render_template(
        "index.html",
        messages=paginated_messages,
        # The in-page search box loads the full list on demand from
        # `/<season>/comunicados/search-data` — keeps the page cheap and
        # only pays the read cost if the user actually searches.
        all_comunicados=[],
        error=error,
        active_page="comunicados",
        current_page=page,
        total_pages=total_pages,
    )


@bp.route("/<season>/comunicados/search-data")
def comunicados_search_data(season: str) -> Response:
    """JSON list of all comunicados for the season — used by the search box.

    The comunicados page renders only the current page (server-side
    pagination), so the in-page search needs the rest on demand. The
    template fetches this endpoint the first time the user focuses the
    search input, caches the response, and filters client-side from then
    on. One full-category read per session, only if someone actually
    searches. `contenido` ships as plain text (~50% smaller payload than
    the sanitized HTML; the search card renders with `whitespace-pre-wrap`
    to keep the line breaks visible).
    """
    try:
        msgs = repository.get_messages_by_category(g.season, "comunicado")
        return jsonify(
            [
                {
                    "id_hash": m.id_hash,
                    "titulo": m.titulo,
                    "autor": m.autor,
                    "fecha": m.fecha,
                    "categoria": m.categoria,
                    "contenido": to_text(m.contenido),
                }
                for m in msgs
            ]
        )
    except Exception:
        logger.exception(
            "Error loading comunicados search-data from Firestore.",
            extra={"season": g.season},
        )
        return jsonify([]), 500


# Front pages change a handful of times a season; the manifest is small and
# public. Cached like the calendar feed so a burst of visits costs one fetch.
_PORTADAS_CACHE_TTL_SECONDS = 600
_portadas_cache: dict[str, tuple[float, list]] = {}


def _fetch_portadas(season: str) -> list:
    """Front pages for a season, newest first. Never raises.

    Reads `periodico/{season}/index.json` from the public bucket — no
    credentials, no listing permission, and no deploy when a new edition is
    published. A missing or malformed manifest means the section simply does
    not render: a league that has not published any is the normal case, and
    is indistinguishable here from one whose manifest is briefly unreachable.
    """
    cached = _portadas_cache.get(season)
    if cached and time.monotonic() - cached[0] < _PORTADAS_CACHE_TTL_SECONDS:
        return cached[1]

    base = f"https://storage.googleapis.com/{config.PERIODICO_BUCKET}/periodico"
    try:
        response = requests.get(f"{base}/{season}/index.json", timeout=5)
        response.raise_for_status()
        entries = response.json()
        portadas = [
            {
                "fecha": e["fecha"],
                "titulo": e.get("titulo", ""),
                "url": f"{base}/{season}/{e['fecha']}.jpg",
            }
            for e in entries
            if e.get("fecha")
        ]
        portadas.sort(key=lambda e: e["fecha"], reverse=True)
    except Exception:
        logger.info("No front pages for this season.", extra={"season": season})
        return []

    _portadas_cache[season] = (time.monotonic(), portadas)
    return portadas


@bp.route("/<season>/salseo")
def salseo(season: str) -> str:
    """Display datos curiosos + crónicas.

    One Firestore query per content type — no full-collection scan.

    Clausulazos and the tabla de justicia used to be read here too and handed
    to a template that renders neither: they live on `/mercado`. Two reads per
    visit went straight to the bin, with an error branch that could never
    surface anything.
    """
    error = None
    datos_curiosos: list = []
    cronicas: list = []
    try:
        datos_curiosos = _sanitize_contenido(
            repository.get_messages_by_category(season, "dato")
        )
        cronicas = _sanitize_contenido(
            repository.get_messages_by_category(season, "cronica")
        )
    except Exception:
        error = f"Ocurrió un error al cargar los datos de la temporada {season}."
        logger.exception(
            "Error loading salseo from Firestore.", extra={"season": season}
        )
    return render_template(
        "salseo.html",
        datos=datos_curiosos,
        cronicas=cronicas,
        portadas=_fetch_portadas(season),
        error=error,
        active_page="salseo",
    )


@bp.route("/<season>/participacion")
def participacion(season: str) -> str:
    """Display participation statistics for a given season.

    Repo returns authors already ordered by `total` DESC (Firestore
    `order_by` on the stored derived field).
    """
    error = None
    stats: list = []
    try:
        stats = [
            {
                "autor": p.autor,
                "comunicados": len(p.comunicados),
                "datos": len(p.datos),
                "cesiones": len(p.cesiones),
                "cronicas": len(p.cronicas),
                "total": p.total,
            }
            for p in repository.get_participaciones(season)
        ]
    except Exception:
        error = (
            f"Ocurrió un error al calcular las estadísticas de la temporada {season}."
        )
        logger.exception(
            "Error loading participacion from Firestore.", extra={"season": season}
        )
    return render_template(
        "participacion.html",
        stats=stats,
        error=error,
        active_page="participacion",
    )


@bp.route("/<season>/mercado")
def mercado(season: str) -> str:
    """Display transfers and justice table for a given season.

    Repo returns clausulazos ordered by `fecha` DESC and tabla_justicia
    by `total_hechos` DESC.
    """
    clausulazos: list = []
    tabla_justicia: list = []
    error = None
    try:
        clausulazos = repository.get_clausulazos(season)
        tabla_justicia = [asdict(e) for e in repository.get_tabla_justicia(season)]
    except Exception:
        error = (
            "Ocurrió un error al cargar los datos del mercado"
            f" de la temporada {season}."
        )
        logger.exception(
            "Error loading mercado from Firestore.", extra={"season": season}
        )

    clausulazos_summary = None
    if clausulazos:
        clausulazos_summary = {
            "total": len(clausulazos),
            "total_eur": sum(c.precio for c in clausulazos),
            "max_clausulazo": max(clausulazos, key=lambda c: c.precio),
            "ultimo": clausulazos[0],
        }

    return render_template(
        "mercado.html",
        clausulazos=clausulazos,
        clausulazos_summary=clausulazos_summary,
        tabla_justicia=tabla_justicia,
        error=error,
        active_page="mercado",
    )


# --- Lloros Awards (Google Sheets) ---------------------------------------


@bp.route("/<season>/lloros-awards")
def lloros_awards(season: str) -> str:
    """Display the Lloros Awards page for a given season, H2H tab first."""
    return _render_awards(season, tab="h2h")


@bp.route("/<season>/h2h")
def h2h(season: str) -> str:
    """Deep link straight to the Liga H2H tab of the awards page.

    H2H lives as a tab rather than a ninth nav entry: the bar is already at
    eight links and this site is read on a phone.
    """
    return _render_awards(season, tab="h2h")


# Order matters: the first tab a season has is the one it opens on. H2H leads
# because it is the competition being played week to week.
_AWARD_TABS = (
    ("h2h", "🤝 Liga H2H", "H2H_SHEETS"),
    ("trofeos", "🥇 Trofeos", "TROFEOS_SHEETS"),
)


def _awards_tabs(season: str) -> list[dict]:
    """The tabs this season actually has, driven by which sheets exist.

    A competition retires by nobody creating its sheet for the new season —
    no code change, no deploy, and the past seasons that do have one keep
    theirs reachable through the season selector. That is why the tab strip
    is derived rather than fixed: the Ligas Especiales ran in 25-26 and not
    in 26-27, and both have to render honestly.
    """
    return [
        {"key": key, "label": label}
        for key, label, sheets in _AWARD_TABS
        if season in getattr(config, sheets)
    ]


def _render_awards(season: str, tab: str) -> str:
    """Render the awards page. Only the H2H tab is server-rendered.

    Trofeos stays lazy — one fetch, and most visits only want the standings.
    H2H is the reason people open this page every week, so it must be in the
    first paint.
    """
    tabs = _awards_tabs(season)
    keys = [t["key"] for t in tabs]
    if tab not in keys:
        tab = keys[0] if keys else ""

    error = None
    if tabs and not services.sheets_service:
        error = "El servicio de Google Sheets no está disponible."

    rounds, issues, h2h_error = _load_h2h(season)
    if h2h_error and not error:
        error = h2h_error

    return render_template(
        "lloros_awards.html",
        leagues=None,
        trofeos=None,
        error=error,
        active_page="lloros_awards",
        tabs=tabs,
        active_tab=tab,
        h2h_played="h2h" in keys,
        h2h_rounds=rounds,
        h2h_standings=h2h_logic.standings(rounds) if rounds else [],
        h2h_issues=issues,
    )


# The organiser reloads to check the score he just typed, so this cache is
# minutes rather than the half-hour the calendar feed gets.
_h2h_cache: dict[str, tuple[float, list, list]] = {}


def invalidate_h2h_cache() -> None:
    """Drop every cached H2H read. Called by the admin panel."""
    _h2h_cache.clear()


def _load_h2h(season: str) -> tuple[list, list[str], str | None]:
    """Rounds, data issues and a user-facing error for one season.

    A season with no sheet configured is not an error — the competition
    started in 26-27 and simply did not exist before. A sheet that is
    configured but unreadable **is**: the page still renders the whole
    calendar without scores, and says why, because the last time a Sheets
    credential died the pages just went blank for a season.
    """
    if season not in config.H2H_SHEETS:
        return [], [], None

    sheet_id = config.H2H_SHEETS.get(season)
    if not sheet_id:
        return (
            h2h_logic.build_rounds({})[0],
            [],
            (
                "Falta la hoja de resultados de esta temporada; "
                "el calendario es el del reglamento."
            ),
        )

    cached = _h2h_cache.get(season)
    if cached and time.monotonic() - cached[0] < config.H2H_CACHE_TTL_SECONDS:
        return cached[1], cached[2], None

    if not services.sheets_service:
        return (
            h2h_logic.build_rounds({})[0],
            [],
            (
                "No se pueden leer los resultados ahora mismo; "
                "el calendario sí está actualizado."
            ),
        )

    try:
        rows = get_sheet_rows(services.sheets_service, sheet_id, config.H2H_SHEET_RANGE)
    except Exception:
        logger.exception("Error loading Liga H2H sheet.", extra={"season": season})
        return (
            h2h_logic.build_rounds({})[0],
            [],
            (
                "No se pueden leer los resultados ahora mismo; "
                "el calendario sí está actualizado."
            ),
        )

    matches, parse_issues = h2h_logic.parse_rows(rows)
    rounds, build_issues = h2h_logic.build_rounds(matches)
    issues = parse_issues + build_issues
    _h2h_cache[season] = (time.monotonic(), rounds, issues)
    return rounds, issues, None


@bp.route("/<season>/api/lloros-awards/trofeos")
def api_lloros_trofeos(season: str) -> Response:
    """Return trophy data as JSON for `season`."""
    trofeos: list = []
    try:
        sheet_id = config.TROFEOS_SHEETS.get(season)
        if sheet_id and services.sheets_service:
            trofeos = get_sheets_data(services.sheets_service, sheet_id)
    except Exception:
        logger.exception("Error loading trofeos.", extra={"season": season})
    return jsonify(trofeos)
