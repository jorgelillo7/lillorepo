"""Admin routes: login panel and logout."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil import parser
from flask import (
    Blueprint,
    Response,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from core.sdk.gcp import get_file_metadata
from packages.biwenger_tools.web import config, services

bp = Blueprint("admin", __name__)

MADRID_TZ = ZoneInfo("Europe/Madrid")


def _get_sheet_file_status(sheet_id: str) -> dict:
    """Fetch metadata for a Google Sheet and return a status dict."""
    sheet_metadata = (
        services.drive_service.files()
        .get(fileId=sheet_id, fields="name, modifiedTime")
        .execute()
    )
    dt_utc = parser.isoparse(sheet_metadata["modifiedTime"])
    dt_madrid = dt_utc.astimezone(MADRID_TZ)
    is_stale = (datetime.now(MADRID_TZ) - dt_madrid) > timedelta(days=7)
    return {
        "name": f"{sheet_metadata['name']} (Sheet)",
        "status": "Encontrado",
        "last_updated": dt_madrid.strftime("%d-%m-%Y a las %H:%M:%S"),
        "is_stale": is_stale,
    }


def _build_file_statuses() -> list:
    """Collect status information for all relevant Drive/Sheets files."""
    comunicados_actual = f"{config.COMUNICADOS_FILENAME_BASE}_{g.season}.csv"
    participacion_actual = f"{config.PARTICIPACION_FILENAME_BASE}_{g.season}.csv"
    filenames = [comunicados_actual, participacion_actual, config.PALMARES_FILENAME]
    dynamic_files = [comunicados_actual, participacion_actual]

    statuses = get_file_metadata(
        services.drive_service, config.GDRIVE_FOLDER_ID, filenames, dynamic_files
    )

    sheet_id = config.LIGAS_ESPECIALES_SHEETS.get(g.season)
    if sheet_id:
        statuses.append(_get_sheet_file_status(sheet_id))

    return statuses


@bp.route("/admin", methods=["GET", "POST"])
def admin() -> Response:
    """Admin panel: login form or file-status dashboard."""
    if "admin_logged_in" in session:
        file_statuses: list = []
        error = None
        try:
            if not services.drive_service:
                raise Exception("El servicio de Google Drive no está disponible.")
            file_statuses = _build_file_statuses()
        except Exception as e:
            error = f"No se pudo conectar con Google Drive: {e}"

        log_url = (
            f"https://console.cloud.google.com/run/jobs/details/"
            f"{config.CLOUD_RUN_REGION}/{config.CLOUD_RUN_JOB_NAME}"
            f"/logs?project={config.GCP_PROJECT_ID}"
        )
        return render_template(
            "admin_panel.html",
            active_page="admin",
            file_statuses=file_statuses,
            log_url=log_url,
            error=error,
        )

    if request.method == "POST":
        if request.form.get("password") == config.ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin.admin"))
        flash("Contraseña incorrecta. Inténtalo de nuevo.", "error")

    return render_template("admin_login.html", active_page="admin")


@bp.route("/logout")
def logout() -> Response:
    """Log out the admin user."""
    session.pop("admin_logged_in", None)
    flash("Has cerrado la sesión correctamente.", "info")
    return redirect(url_for("main.home"))
