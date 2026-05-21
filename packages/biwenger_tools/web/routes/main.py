"""Main routes: home, favicon, palmares, reglamento."""

import ssl
from collections import defaultdict

from flask import Blueprint, Response, g, jsonify, redirect, render_template, url_for

from core.sdk.gcp import download_csv_as_dict, find_file_on_drive, get_sheets_data
from core.utils import get_logger
from packages.biwenger_tools.web import config, repository, services

logger = get_logger(__name__)
bp = Blueprint("main", __name__)


@bp.route("/version")
def version() -> Response:
    """Return the deployed git commit SHA."""
    return jsonify({"commit": config.GIT_COMMIT})


@bp.route("/favicon.ico")
@bp.route("/favicon.ico/")
def favicon() -> tuple:
    """Return empty response for favicon requests."""
    return "", 204


@bp.route("/")
def home() -> Response:
    """Redirect to the current season's comunicados page."""
    return redirect(url_for("season.comunicados", season=g.season))


def _palmares_firestore() -> str:
    """Firestore-backed version of the palmares route.

    Reshapes each `Palmares` document into the dict the template expects:
    direct keys for the podium/season data and an `otros` list for the
    "les toca pagar a" block (multas + farolillo). `repository.get_palmares`
    returns rows ordered by season DESC, so no Python sort here.
    """
    error = None
    sorted_seasons: list = []
    try:
        sorted_seasons = []
        for p in repository.get_palmares():
            otros = [{"tipo": "multa", "valor": m} for m in p.multas]
            if p.farolillo:
                otros.append({"tipo": "farolillo", "valor": p.farolillo})
            sorted_seasons.append(
                (
                    p.temporada,
                    {
                        "campeon": p.campeon,
                        "subcampeon": p.subcampeon,
                        "tercero": p.tercero,
                        "puntuacion": p.puntuacion,
                        "record_puntos": p.record_puntos,
                        "jornadas_ganadas": p.jornadas_ganadas,
                        "otros": otros,
                    },
                )
            )
    except Exception:
        error = "Ocurrió un error al cargar el palmarés."
        logger.exception("Error loading palmares from Firestore.")

    return render_template(
        "palmares.html",
        seasons=sorted_seasons,
        error=error,
        active_page="palmares",
    )


@bp.route("/palmares")
def palmares() -> str:
    """Display historical records and awards."""
    if config.DATA_BACKEND == "firestore":
        return _palmares_firestore()
    seasons: dict = defaultdict(lambda: defaultdict(list))
    error = None
    sorted_seasons: list = []
    try:
        if not services.drive_service:
            raise Exception("El servicio de Google Drive no está disponible.")

        file_metadata = find_file_on_drive(
            services.drive_service, config.PALMARES_FILENAME, config.GDRIVE_FOLDER_ID
        )
        if not file_metadata:
            raise FileNotFoundError(
                f"El archivo '{config.PALMARES_FILENAME}' "
                "no se encontró en Google Drive."
            )

        palmares_data = download_csv_as_dict(
            services.drive_service, file_metadata["id"]
        )
        for row in palmares_data:
            season_data = row.get("temporada", "").strip()
            category = row.get("categoria", "").strip()
            value = row.get("valor", "").strip()
            if not season_data or not category:
                continue
            if category in ["multa", "sancion", "farolillo"]:
                seasons[season_data]["otros"].append({"tipo": category, "valor": value})
            else:
                seasons[season_data][category] = value
        sorted_seasons = sorted(seasons.items(), key=lambda item: item[0], reverse=True)
    except ssl.SSLError:
        error = "Error de SSL al conectar con Google Drive."
        logger.exception("SSL error loading palmares.")
    except Exception:
        error = "Ocurrió un error al cargar el palmarés."
        logger.exception("Error loading palmares.")

    return render_template(
        "palmares.html",
        seasons=sorted_seasons,
        error=error,
        active_page="palmares",
    )


@bp.route("/reglamento")
def reglamento() -> str:
    """Display the rules page."""
    error = None
    leagues: list = []
    try:
        if services.sheets_service:
            sheet_id = config.LIGAS_ESPECIALES_SHEETS.get(g.season)
            if sheet_id:
                leagues = get_sheets_data(services.sheets_service, sheet_id)
    except ssl.SSLError:
        error = "Error de SSL al conectar con Google Sheets."
        logger.exception("SSL error loading reglamento.")
    except Exception:
        error = "Ocurrió un error al cargar los datos para el reglamento."
        logger.exception("Error loading reglamento.")

    return render_template(
        "reglamento.html",
        leagues=leagues,
        error=error,
        active_page="reglamento",
    )
