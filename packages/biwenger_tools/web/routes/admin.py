"""Admin routes: login panel, logout, and on-demand scraper trigger."""

from datetime import datetime

import google.auth
import google.auth.exceptions
import google.auth.transport.requests
import requests as http_requests
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

from core.constants import DRIVE_STALE_THRESHOLD, MADRID_TZ
from core.sdk.gcp import get_file_metadata
from core.utils import get_logger
from packages.biwenger_tools.web import config, services
from packages.biwenger_tools.web.csrf import verify_csrf_token

bp = Blueprint("admin", __name__)
logger = get_logger(__name__)

_CLOUD_RUN_JOBS_API = (
    "https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run"
)


def _get_sheet_file_status(sheet_id: str) -> dict:
    """Fetch metadata for a Google Sheet and return a status dict."""
    sheet_metadata = (
        services.drive_service.files()
        .get(fileId=sheet_id, fields="name, modifiedTime")
        .execute()
    )
    dt_utc = parser.isoparse(sheet_metadata["modifiedTime"])
    dt_madrid = dt_utc.astimezone(MADRID_TZ)
    is_stale = (datetime.now(MADRID_TZ) - dt_madrid) > DRIVE_STALE_THRESHOLD
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


def _trigger_scraper_job() -> tuple[bool, str]:
    """
    Trigger the scraper Cloud Run Job via the Cloud Run API v2.
    Returns (success, message).
    Uses ADC — works in Cloud Run if the service SA has roles/run.developer.
    """
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)

        url = _CLOUD_RUN_JOBS_API.format(
            project=config.GCP_PROJECT_ID,
            region=config.CLOUD_RUN_REGION,
            job=config.CLOUD_RUN_JOB_NAME,
        )
        resp = http_requests.post(
            url,
            headers={"Authorization": f"Bearer {credentials.token}"},
            json={},
            timeout=15,
        )
        resp.raise_for_status()
        execution_name = resp.json().get("name", "").split("/")[-1]
        logger.info("Scraper job triggered.", extra={"execution": execution_name})
        return True, f"Job lanzado correctamente (ejecución: {execution_name})."
    except (
        google.auth.exceptions.GoogleAuthError,
        http_requests.RequestException,
    ) as exc:
        logger.error("Failed to trigger scraper job.", extra={"error": str(exc)})
        return False, f"Error al lanzar el job: {exc}"


@bp.route("/admin", methods=["GET", "POST"])
def admin() -> Response:
    """Admin panel: login form or VAR dashboard."""
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
            gcp_project=config.GCP_PROJECT_ID,
            cloud_run_region=config.CLOUD_RUN_REGION,
            job_name=config.CLOUD_RUN_JOB_NAME,
        )

    if request.method == "POST":
        if not verify_csrf_token():
            logger.warning(
                "CSRF token mismatch on /admin login.",
                extra={"remote_addr": request.remote_addr},
            )
            flash("Sesión expirada. Vuelve a intentarlo.", "error")
            return redirect(url_for("admin.admin"))
        if request.form.get("password") == config.ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin.admin"))
        flash("Contraseña incorrecta. Inténtalo de nuevo.", "error")

    return render_template("admin_login.html", active_page="admin")


@bp.route("/admin/run-scraper", methods=["POST"])
def run_scraper() -> Response:
    """Trigger the scraper Cloud Run Job on demand."""
    if "admin_logged_in" not in session:
        flash("Acceso denegado.", "error")
        return redirect(url_for("admin.admin"))

    if not verify_csrf_token():
        logger.warning(
            "CSRF token mismatch on /admin/run-scraper.",
            extra={"remote_addr": request.remote_addr},
        )
        flash("Sesión expirada. Recarga la página y vuelve a intentarlo.", "error")
        return redirect(url_for("admin.admin"))

    success, message = _trigger_scraper_job()
    flash(message, "success" if success else "error")
    return redirect(url_for("admin.admin"))


@bp.route("/logout")
def logout() -> Response:
    """Log out the admin user."""
    session.pop("admin_logged_in", None)
    flash("Has cerrado la sesión correctamente.", "info")
    return redirect(url_for("main.home"))
