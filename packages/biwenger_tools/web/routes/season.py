"""Season-scoped routes: comunicados, salseo, participacion, mercado,
lloros_awards, and their API endpoints.

Data flow:
- Content (comunicados/datos/cronicas/clausulazos/participacion/tabla)
  comes from Firestore via `repository.*`. Filtering, ordering, and
  pagination all happen server-side — see the inline queries there.
- Lloros Awards (ligas especiales + trofeos) still come from Google
  Sheets — hand-edited by the user, not part of the Firestore data set.
"""

from dataclasses import asdict

from flask import Blueprint, Response, g, jsonify, render_template, request

from core.sdk.gcp import get_sheets_data
from core.utils import get_logger
from packages.biwenger_tools.web import config, repository, services
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


@bp.route("/<season>/salseo")
def salseo(season: str) -> str:
    """Display datos curiosos + crónicas + clausulazos + tabla de justicia.

    One Firestore query per content type — no full-collection scan.
    """
    error = None
    clausulazos_error = None
    datos_curiosos: list = []
    cronicas: list = []
    clausulazos: list = []
    tabla_justicia: list = []
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
    try:
        clausulazos = repository.get_clausulazos(season)
        tabla_justicia = [asdict(e) for e in repository.get_tabla_justicia(season)]
    except Exception:
        clausulazos_error = "Error al cargar clausulazos."
        logger.exception(
            "Error loading clausulazos from Firestore.", extra={"season": season}
        )
    return render_template(
        "salseo.html",
        datos=datos_curiosos,
        cronicas=cronicas,
        clausulazos=clausulazos,
        tabla_justicia=tabla_justicia,
        clausulazos_error=clausulazos_error,
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
    """Display the Lloros Awards page for a given season."""
    error = None
    if not services.sheets_service:
        error = "El servicio de Google Sheets no está disponible."

    return render_template(
        "lloros_awards.html",
        leagues=None,
        trofeos=None,
        error=error,
        active_page="lloros_awards",
    )


@bp.route("/api/lloros-awards/ligas")
def api_lloros_ligas() -> Response:
    """Return league data as JSON for the current season."""
    leagues: list = []
    try:
        sheet_id = config.LIGAS_ESPECIALES_SHEETS.get(g.season)
        if sheet_id and services.sheets_service:
            leagues = get_sheets_data(services.sheets_service, sheet_id)
    except Exception:
        logger.exception("Error loading ligas especiales.", extra={"season": g.season})
    return jsonify(leagues)


@bp.route("/api/lloros-awards/trofeos")
def api_lloros_trofeos() -> Response:
    """Return trophy data as JSON for the current season."""
    trofeos: list = []
    try:
        sheet_id = config.TROFEOS_SHEETS.get(g.season)
        if sheet_id and services.sheets_service:
            trofeos = get_sheets_data(services.sheets_service, sheet_id)
    except Exception:
        logger.exception("Error loading trofeos.", extra={"season": g.season})
    return jsonify(trofeos)
