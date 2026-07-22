"""Main routes: home, favicon, palmares, reglamento, calendario."""

import calendar
import ssl
import time
from datetime import date, datetime

import icalendar
import requests
from dateutil.rrule import rrulestr
from flask import (
    Blueprint,
    Response,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    url_for,
)

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

# Category detection is keyword-based: the public .ics feed carries no
# CATEGORIES/COLOR field (Google only exposes per-event color via the paid
# Calendar API), but event titles already follow a stable naming convention
# ("Liga J3", "Copa Santa Claus - J4", "H2H J1"...). Order matters: first
# keyword match wins. See DESIGN.md "Calendar category colours".
_CATEGORY_KEYWORDS = [
    ("liga", "liga"),
    ("copa", "copa"),
    ("h2h", "h2h"),
    ("mercado", "mercado"),
    ("draft", "draft"),
]
_CATEGORY_STYLES = {
    "liga": {"label": "Liga", "chip": "bg-green-100 text-green-800 border-green-200"},
    "copa": {"label": "Copa", "chip": "bg-amber-100 text-amber-800 border-amber-200"},
    "h2h": {"label": "H2H", "chip": "bg-blue-100 text-blue-800 border-blue-200"},
    "mercado": {"label": "Mercado", "chip": "bg-red-100 text-red-800 border-red-200"},
    "draft": {
        "label": "Draft",
        "chip": "bg-purple-100 text-purple-800 border-purple-200",
    },
    "otros": {"label": "Otros", "chip": "bg-gray-100 text-gray-700 border-gray-200"},
}
_CATEGORY_ORDER = ["liga", "copa", "h2h", "mercado", "draft", "otros"]


def _categorize(title: str) -> str:
    """Map an event title to a category key via keyword match, else `otros`."""
    lowered = title.lower()
    for keyword, category in _CATEGORY_KEYWORDS:
        if keyword in lowered:
            return category
    return "otros"


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


def _month_events(year: int, month: int) -> dict[date, list[dict]]:
    """Map each date in `year`-`month` to the events occurring on it.

    Each event is `{title, time, description, location}` — `time` is
    `None` for all-day events. Expands `RRULE` recurrences via
    `dateutil`; all-day and timed `VEVENT`s are both reduced to a plain
    `date` in Madrid time for bucketing.
    """
    cal = icalendar.Calendar.from_ical(_fetch_calendar_ics())

    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    events: dict[date, list[dict]] = {}
    for component in cal.walk("VEVENT"):
        dtstart_raw = component.get("DTSTART").dt
        if isinstance(dtstart_raw, datetime):
            local_start = dtstart_raw.astimezone(MADRID_TZ)
            dtstart_date = local_start.date()
            event_time = local_start.strftime("%H:%M")
        else:
            dtstart_date = dtstart_raw
            event_time = None

        title = str(component.get("SUMMARY", ""))
        event = {
            "title": title,
            "time": event_time,
            "description": str(component.get("DESCRIPTION", "")),
            "location": str(component.get("LOCATION", "")),
            "category": _categorize(title),
        }

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
            events.setdefault(day, []).append(event)

    return events


@bp.route("/calendario")
@bp.route("/calendario/<int:year>/<int:month>")
def calendario(year: int | None = None, month: int | None = None) -> str:
    """Display the league's public Google Calendar for a given month.

    Defaults to the current month (Madrid time). Read-only viewer with
    month navigation; event titles are clickable to reveal their detail.
    """
    today = datetime.now(MADRID_TZ).date()
    if year is None or month is None:
        year, month = today.year, today.month
    try:
        date(year, month, 1)
    except ValueError:
        abort(404)

    error = None
    events: dict[date, list[dict]] = {}
    try:
        events = _month_events(year, month)
    except Exception:
        error = "No se ha podido cargar el calendario."
        logger.exception("Error loading league calendar.")

    weeks = [
        [
            {
                "date": day,
                "in_month": day.month == month,
                "is_today": day == today,
                "events": events.get(day, []),
            }
            for day in week
        ]
        for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    ]
    events_by_day = {day.isoformat(): day_events for day, day_events in events.items()}

    categories_present = {
        e["category"] for day_events in events.values() for e in day_events
    }
    categories = [
        {"key": key, **_CATEGORY_STYLES[key]}
        for key in _CATEGORY_ORDER
        if key in categories_present
    ]

    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    return render_template(
        "calendario.html",
        weeks=weeks,
        weekday_labels=_WEEKDAY_LABELS_ES,
        month_label=f"{_MONTHS_ES[month]} {year}",
        events_by_day=events_by_day,
        categories=categories,
        category_styles=_CATEGORY_STYLES,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        is_current_month=(year == today.year and month == today.month),
        error=error,
        active_page="calendario",
    )
