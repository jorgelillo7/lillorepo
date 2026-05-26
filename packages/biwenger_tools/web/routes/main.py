"""Main routes: home, favicon, palmares, reglamento."""

import ssl

from flask import Blueprint, Response, g, jsonify, redirect, render_template, url_for

from core.sdk.gcp import get_sheets_data
from core.utils import get_logger
from packages.biwenger_tools.web import config, repository, services

logger = get_logger(__name__)
bp = Blueprint("main", __name__)


def _display_season(season: str) -> str:
    """Expand ``25-26`` → ``2025-2026`` for the palmares heading.

    Legacy docs already store the long form (``2024-2025``) — those pass
    through untouched. Only the short ``YY-YY`` Firestore doc ids written
    by the season-rollover skill get expanded.
    """
    if (
        len(season) == 5
        and season[2] == "-"
        and season[:2].isdigit()
        and season[3:].isdigit()
    ):
        return f"20{season[:2]}-20{season[3:]}"
    return season


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


@bp.route("/palmares")
def palmares() -> str:
    """Display historical records and awards.

    Reshapes each `Palmares` document into the dict the template expects:
    direct keys for the podium/season data and an `otros` list for the
    "les toca pagar a" block (multas + farolillo). `repository.get_palmares`
    already returns rows sorted by season DESC, no Python sort here.
    """
    error = None
    sorted_seasons: list = []
    try:
        for p in repository.get_palmares():
            n = len(p.standings_table)
            winners_count = n // 2
            neutros_count = n % 2
            annotated_rows = []
            for s in p.standings_table:
                if s.note:
                    tier = "loser"
                elif s.position <= winners_count:
                    tier = "winner"
                elif s.position > winners_count + neutros_count:
                    tier = "loser"
                else:
                    tier = "neutro"
                annotated_rows.append(
                    {
                        "position": s.position,
                        "real_name": s.real_name,
                        "team_name": s.team_name,
                        "points": s.points,
                        "best_round": s.best_round,
                        "worst_round": s.worst_round,
                        "rounds_won": s.rounds_won,
                        "avg_position": s.avg_position,
                        "note": s.note,
                        "tier": tier,
                    }
                )
            farolillo_name = p.multas[-1] if p.multas else ""
            farolillo_note = next(
                (
                    s.note
                    for s in p.standings_table
                    if s.real_name == farolillo_name and s.note
                ),
                "",
            )
            sorted_seasons.append(
                (
                    p.temporada,
                    {
                        "display_season": _display_season(p.temporada),
                        "campeon": p.campeon,
                        "subcampeon": p.subcampeon,
                        "tercero": p.tercero,
                        "puntuacion": p.puntuacion,
                        "record_puntos": p.record_puntos,
                        "jornadas_ganadas": p.jornadas_ganadas,
                        "clausulazos_total": p.clausulazos_total,
                        "standings_table": annotated_rows,
                        "multas": p.multas,
                        "farolillo_note": farolillo_note,
                        "neutros": p.neutros,
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
