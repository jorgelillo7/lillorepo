"""Admin routes: login panel, logout, and on-demand scraper trigger."""

import hmac

import google.auth.exceptions
import requests as http_requests
from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from core.sdk.gcp import trigger_cloud_run_job
from core.utils import get_logger
from packages.biwenger_tools.web import config
from core.web.csrf import verify_csrf_token
from core.web.ratelimit import RateLimiter

bp = Blueprint("admin", __name__)
logger = get_logger(__name__)

# A password form on the open internet gets brute-forced eventually;
# a per-IP sliding window blunts it (per instance — good enough here).
_LOGIN_LIMITER = RateLimiter(10, 900)


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr or "?"


def _trigger_scraper_job() -> tuple[bool, str]:
    """Trigger the scraper Cloud Run Job. Returns (success, message)."""
    try:
        execution_name = trigger_cloud_run_job(
            config.GCP_PROJECT_ID, config.CLOUD_RUN_REGION, config.CLOUD_RUN_JOB_NAME
        )
        return True, f"Job lanzado correctamente (ejecución: {execution_name})."
    except (
        google.auth.exceptions.GoogleAuthError,
        http_requests.RequestException,
    ) as exc:
        logger.error("Failed to trigger scraper job.", extra={"error": str(exc)})
        return False, f"Error al lanzar el job: {exc}"


@bp.route("/admin", methods=["GET", "POST"])
def admin() -> Response:
    """Admin panel: login form or scraper-trigger dashboard."""
    if "admin_logged_in" in session:
        log_url = (
            f"https://console.cloud.google.com/run/jobs/details/"
            f"{config.CLOUD_RUN_REGION}/{config.CLOUD_RUN_JOB_NAME}"
            f"/logs?project={config.GCP_PROJECT_ID}"
        )
        return render_template(
            "admin_panel.html",
            active_page="admin",
            log_url=log_url,
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
        if not _LOGIN_LIMITER.allow(_client_ip()):
            logger.warning("Admin login rate-limited.", extra={"ip": _client_ip()})
            flash("Demasiados intentos — espera unos minutos.", "error")
            return redirect(url_for("admin.admin"))
        # compare_digest: a plain == leaks the match length through timing.
        if hmac.compare_digest(
            request.form.get("password") or "", config.ADMIN_PASSWORD or ""
        ):
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
