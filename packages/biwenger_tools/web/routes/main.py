"""Main routes: home, favicon, palmares, reglamento, calendario."""

import calendar
import ssl
import time
from datetime import date, datetime

import icalendar
import requests
from dateutil.rrule import rrulestr
from flask import Blueprint, Response, g, jsonify, redirect, render_template, url_for

from core.constants import MADRID_TZ
from core.sdk.gcp import get_sheets_data
from core.sdk.http import retry_http_request
from core.utils import get_logger
from packages.biwenger_tools.web import config, repository, services

logger = get_logger(__name__)
bp = Blueprint("main", __name__)

# Public "Lloros League" Google Calendar — read-only, season-agnostic.
# Public by design (see Google Calendar sharing settings), so no secret
# management needed for this URL.
CALENDAR_ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "9be2a252ae966f7166d9b2a91491f5f3666b5d86096e1bc942717fca559d474f"
    "%40group.calendar.google.com/public/basic.ics"
)

_CALENDAR_CACHE_TTL_SECONDS = 30 * 60
_calendar_cache: dict = {"fetched_at": 0.0, "raw": None}

_MONTHS_ES = [
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]
_WEEKDAY_LABELS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


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


def _fetch_calendar_ics() -> bytes:
    """Fetch the league's public .ics feed, cached for `_CALENDAR_CACHE_TTL_SECONDS`."""
    now = time.monotonic()
    if (
        _calendar_cache["raw"] is not None
        and now - _calendar_cache["fetched_at"] < _CALENDAR_CACHE_TTL_SECONDS
    ):
        return _calendar_cache["raw"]

    response = retry_http_request(
        lambda: requests.get(CALENDAR_ICS_URL, timeout=10),
        label="league calendar ics fetch",
    )
    _calendar_cache["raw"] = response.content
    _calendar_cache["fetched_at"] = now
    return _calendar_cache["raw"]


def _month_events(year: int, month: int) -> dict[date, list[str]]:
    """Map each date in `year`-`month` to the titles of events occurring on it.

    Expands `RRULE` recurrences via `dateutil`; all-day and timed `VEVENT`s
    are both reduced to a plain `date` in Madrid time.
    """
    cal = icalendar.Calendar.from_ical(_fetch_calendar_ics())

    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    events: dict[date, list[str]] = {}
    for component in cal.walk("VEVENT"):
        summary = str(component.get("SUMMARY", ""))
        dtstart_raw = component.get("DTSTART").dt
        if isinstance(dtstart_raw, datetime):
            dtstart_date = dtstart_raw.astimezone(MADRID_TZ).date()
        else:
            dtstart_date = dtstart_raw

        rrule = component.get("RRULE")
        if rrule:
            window_start = datetime.combine(month_start, datetime.min.time())
            window_end = datetime.combine(month_end, datetime.max.time())
            dtstart_dt = datetime.combine(dtstart_date, datetime.min.time())
            occurrence_dates = [
                occurrence.date()
                for occurrence in rrulestr(
                    rrule.to_ical().decode(), dtstart=dtstart_dt
                ).between(window_start, window_end, inc=True)
            ]
        elif month_start <= dtstart_date <= month_end:
            occurrence_dates = [dtstart_date]
        else:
            occurrence_dates = []

        for day in occurrence_dates:
            events.setdefault(day, []).append(summary)

    return events


@bp.route("/calendario")
def calendario() -> str:
    """Display the league's public Google Calendar for the current month.

    Read-only viewer, season-agnostic: always shows today's month, no
    navigation between months.
    """
    today = datetime.now(MADRID_TZ).date()
    error = None
    events: dict[date, list[str]] = {}
    try:
        events = _month_events(today.year, today.month)
    except Exception:
        error = "No se ha podido cargar el calendario."
        logger.exception("Error loading league calendar.")

    weeks = [
        [
            {
                "date": day,
                "in_month": day.month == today.month,
                "is_today": day == today,
                "events": events.get(day, []),
            }
            for day in week
        ]
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(
            today.year, today.month
        )
    ]

    return render_template(
        "calendario.html",
        weeks=weeks,
        weekday_labels=_WEEKDAY_LABELS_ES,
        month_label=f"{_MONTHS_ES[today.month]} {today.year}",
        error=error,
        active_page="calendario",
    )
