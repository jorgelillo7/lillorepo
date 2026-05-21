"""Season-scoped routes: comunicados, salseo, participacion, lloros_awards, and API."""

import ssl
from dataclasses import asdict
from datetime import datetime
from typing import Optional

from flask import Blueprint, Response, g, jsonify, render_template, request

from core.domain.models import Clausulazo, JusticeEntry, LeagueMessage, Participation
from core.sdk.gcp import download_csv_as_dict, find_file_on_drive, get_sheets_data
from core.utils import get_logger
from packages.biwenger_tools.web import config, repository, services
from packages.biwenger_tools.web.sanitize import safe_html, to_text

logger = get_logger(__name__)
bp = Blueprint("season", __name__)


def _load_messages(filename: str) -> tuple[list, Optional[str]]:
    """Load all LeagueMessage entries from a Drive CSV. Returns (messages, error).

    `contenido` is stripped of its HTML markup eagerly here: every caller either
    renders it through the `safe_html` Jinja filter or ships it to the browser
    via `tojson` to be assigned with `innerHTML`. Sanitizing once at load time
    makes both paths XSS-safe regardless of what Biwenger writes upstream.
    """
    if not services.drive_service:
        return [], "El servicio de Google Drive no está disponible."
    file_meta = find_file_on_drive(
        services.drive_service, filename, config.GDRIVE_FOLDER_ID
    )
    if not file_meta:
        return [], f"El archivo '{filename}' no se encontró en Google Drive."
    rows = download_csv_as_dict(services.drive_service, file_meta["id"])
    messages = [LeagueMessage.from_csv_row(r) for r in rows]
    for m in messages:
        # Pre-render as HTML-escaped Markup with <br> for newlines so the
        # value is safe for both server-side rendering and the JS innerHTML
        # paths that pull it via `{{ ... | tojson }}`.
        m.contenido = str(safe_html(m.contenido))
    return messages, None


# --- Firestore backend ----------------------------------------------------
# These companions back the `DATA_BACKEND=firestore` branch. The CSV route
# bodies below are left untouched so the existing tests keep passing; the
# whole CSV path is removed once the migration flag is retired.
#
# Filtering, ordering, and pagination happen server-side via
# `repository.get_messages_by_category` and friends — see that module for
# the Firestore queries themselves. The routes only stitch them into the
# template payload.


def _sanitize_contenido(messages: list) -> list:
    """Pre-render `contenido` as HTML-escaped Markup with <br> for newlines.

    Templates either render it via the `safe_html` Jinja filter or ship it
    to JS via `tojson` for `innerHTML`; doing the sanitization on read makes
    both paths XSS-safe regardless of what Biwenger writes upstream.
    """
    for m in messages:
        m.contenido = str(safe_html(m.contenido))
    return messages


def _comunicados_firestore(season: str) -> str:
    """Firestore-backed comunicados route — server-side paginated."""
    error = None
    paginated_messages: list = []
    page = 1
    total_pages = 1
    total = 0
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
        # `all_comunicados` powered the global search dropdown when reads were
        # cheap (a single CSV download). With Firestore it would mean pulling
        # the full collection on every page load, defeating the pagination.
        # Templates fall back to an empty list, the search box stays.
        all_comunicados=[],
        error=error,
        active_page="comunicados",
        current_page=page,
        total_pages=total_pages,
    )


def _salseo_firestore(season: str) -> str:
    """Firestore-backed salseo route — one query per content type."""
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


def _participacion_firestore(season: str) -> str:
    """Firestore-backed participacion route — repo orders by `total` DESC."""
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


def _mercado_firestore(season: str) -> str:
    """Firestore-backed mercado route — repo orders by `fecha` DESC."""
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


@bp.route("/<season>/")
def comunicados(season: str) -> str:
    """Display paginated announcements for a given season."""
    if config.DATA_BACKEND == "firestore":
        return _comunicados_firestore(g.season)
    error = None
    paginated_messages: list = []
    comunicados_only: list = []
    page = 1
    total_pages = 1
    try:
        filename = f"{config.COMUNICADOS_FILENAME_BASE}_{g.season}.csv"
        all_messages, err = _load_messages(filename)
        if err:
            raise Exception(err)
        comunicados_only = [
            m for m in all_messages if m.categoria.strip() == "comunicado"
        ]
        page = request.args.get("page", 1, type=int)
        start = (page - 1) * config.MESSAGES_PER_PAGE
        paginated_messages = comunicados_only[start : start + config.MESSAGES_PER_PAGE]
        total_pages = max(
            1,
            (len(comunicados_only) + config.MESSAGES_PER_PAGE - 1)
            // config.MESSAGES_PER_PAGE,
        )
    except ssl.SSLError:
        error = "Error de SSL al conectar con Google Drive."
        logger.exception("SSL error loading comunicados.", extra={"season": g.season})
    except Exception:
        error = (
            f"Ocurrió un error al cargar los comunicados de la temporada {g.season}."
        )
        logger.exception("Error loading comunicados.", extra={"season": g.season})

    return render_template(
        "index.html",
        messages=paginated_messages,
        all_comunicados=comunicados_only,
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
    on. One full-collection read per session, only if someone actually
    searches.

    Only implemented for the Firestore backend; on CSV the comunicados
    route already loads everything (legacy behaviour stays until the CSV
    path is removed).
    """
    if config.DATA_BACKEND != "firestore":
        return jsonify([])
    try:
        msgs = repository.get_messages_by_category(g.season, "comunicado")
        # Plain text instead of HTML: ~50% less on the wire and search
        # filters on text content anyway. The search card renders with
        # `whitespace-pre-wrap` to keep the `\n` line breaks visible.
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
    """Display various categories of content for a given season."""
    if config.DATA_BACKEND == "firestore":
        return _salseo_firestore(g.season)
    error = None
    datos_curiosos: list = []
    cronicas: list = []
    clausulazos: list = []
    tabla_justicia: list = []
    clausulazos_error = None

    try:
        filename = f"{config.COMUNICADOS_FILENAME_BASE}_{g.season}.csv"
        all_messages, err = _load_messages(filename)
        if err:
            raise Exception(err)
        datos_curiosos = [m for m in all_messages if m.categoria.strip() == "dato"]
        cronicas = [m for m in all_messages if m.categoria.strip() == "cronica"]
    except ssl.SSLError:
        error = "Error de SSL al conectar con Google Drive."
        logger.exception("SSL error loading salseo.", extra={"season": g.season})
    except Exception:
        error = f"Ocurrió un error al cargar los datos de la temporada {g.season}."
        logger.exception("Error loading salseo.", extra={"season": g.season})

    try:
        if services.drive_service:
            clausulazos_meta = find_file_on_drive(
                services.drive_service,
                f"{config.CLAUSULAZOS_FILENAME_BASE}_{g.season}.csv",
                config.GDRIVE_FOLDER_ID,
            )
            if clausulazos_meta:
                rows = download_csv_as_dict(
                    services.drive_service, clausulazos_meta["id"]
                )
                clausulazos = [Clausulazo.from_csv_row(r) for r in rows]

            tabla_meta = find_file_on_drive(
                services.drive_service,
                f"{config.TABLA_JUSTICIA_FILENAME_BASE}_{g.season}.csv",
                config.GDRIVE_FOLDER_ID,
            )
            if tabla_meta:
                rows = download_csv_as_dict(services.drive_service, tabla_meta["id"])
                # JS in salseo.html consumes this via {{ tojson }}, so flatten to dicts.
                tabla_justicia = [asdict(JusticeEntry.from_csv_row(r)) for r in rows]
    except Exception:
        clausulazos_error = "Error al cargar clausulazos."
        logger.exception("Error loading clausulazos.", extra={"season": g.season})

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
    """Display participation statistics for a given season."""
    if config.DATA_BACKEND == "firestore":
        return _participacion_firestore(g.season)
    error = None
    stats: list = []
    try:
        if not services.drive_service:
            raise Exception("El servicio de Google Drive no está disponible.")
        filename = f"{config.PARTICIPACION_FILENAME_BASE}_{g.season}.csv"
        file_meta = find_file_on_drive(
            services.drive_service, filename, config.GDRIVE_FOLDER_ID
        )
        if not file_meta:
            raise Exception(f"El archivo '{filename}' no se encontró en Google Drive.")
        rows = download_csv_as_dict(services.drive_service, file_meta["id"])
        participations = [Participation.from_csv_row(r) for r in rows]
        stats = [
            {
                "autor": p.autor,
                "comunicados": len(p.comunicados),
                "datos": len(p.datos),
                "cesiones": len(p.cesiones),
                "cronicas": len(p.cronicas),
                "total": p.total,
            }
            for p in participations
        ]
        stats.sort(key=lambda item: item["total"], reverse=True)
    except ssl.SSLError:
        error = "Error de SSL al conectar con Google Drive."
        logger.exception("SSL error loading participacion.", extra={"season": g.season})
    except Exception:
        error = (
            f"Ocurrió un error al calcular las estadísticas de la temporada {g.season}."
        )
        logger.exception("Error loading participacion.", extra={"season": g.season})

    return render_template(
        "participacion.html",
        stats=stats,
        error=error,
        active_page="participacion",
    )


@bp.route("/<season>/mercado")
def mercado(season: str) -> str:
    """Display transfers and justice table for a given season."""
    if config.DATA_BACKEND == "firestore":
        return _mercado_firestore(g.season)
    clausulazos: list = []
    tabla_justicia: list = []
    error = None
    try:
        if not services.drive_service:
            raise Exception("El servicio de Google Drive no está disponible.")

        clausulazos_meta = find_file_on_drive(
            services.drive_service,
            f"{config.CLAUSULAZOS_FILENAME_BASE}_{g.season}.csv",
            config.GDRIVE_FOLDER_ID,
        )
        if clausulazos_meta:
            rows = download_csv_as_dict(services.drive_service, clausulazos_meta["id"])
            clausulazos = [Clausulazo.from_csv_row(r) for r in rows]

        tabla_meta = find_file_on_drive(
            services.drive_service,
            f"{config.TABLA_JUSTICIA_FILENAME_BASE}_{g.season}.csv",
            config.GDRIVE_FOLDER_ID,
        )
        if tabla_meta:
            rows = download_csv_as_dict(services.drive_service, tabla_meta["id"])
            tabla_justicia = [asdict(JusticeEntry.from_csv_row(r)) for r in rows]
    except Exception:
        error = (
            "Ocurrió un error al cargar los datos del mercado"
            f" de la temporada {g.season}."
        )
        logger.exception("Error loading mercado.", extra={"season": g.season})

    clausulazos_summary = None
    if clausulazos:

        def _parse_fecha(f: str) -> datetime:
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(f, fmt)
                except ValueError:
                    continue
            return datetime.min

        clausulazos_by_date = sorted(
            clausulazos, key=lambda c: _parse_fecha(c.fecha), reverse=True
        )
        clausulazos_summary = {
            "total": len(clausulazos),
            "total_eur": sum(c.precio for c in clausulazos),
            "max_clausulazo": max(clausulazos, key=lambda c: c.precio),
            "ultimo": clausulazos_by_date[0],
        }

    return render_template(
        "mercado.html",
        clausulazos=clausulazos,
        clausulazos_summary=clausulazos_summary,
        tabla_justicia=tabla_justicia,
        error=error,
        active_page="mercado",
    )


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
