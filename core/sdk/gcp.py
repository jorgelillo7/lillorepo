import google.auth
import google.auth.exceptions
import google.auth.transport.requests
import requests as http_requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

from core.utils import get_logger

logger = get_logger(__name__)


# --- AUTHENTICATION ---


def get_google_service(api_name, api_version, service_account_file, scopes):
    """Returns an authenticated client using a Service Account.

    Used for the Google Sheets reader (ligas especiales / trofeos). The
    Drive/CSV pipeline retired with the Firestore migration, so the
    `drive` API client lives elsewhere and only the `sheets` client uses
    this any more — kept generic in case another Google API ever joins.
    """
    credentials = service_account.Credentials.from_service_account_file(
        service_account_file, scopes=scopes
    )
    return build(api_name, api_version, credentials=credentials)


# --- CLOUD RUN JOBS ---

_CLOUD_RUN_JOBS_API = (
    "https://run.googleapis.com/v2/projects/{project}/locations/{region}"
    "/jobs/{job}:run"
)


def trigger_cloud_run_job(project: str, region: str, job_name: str) -> str:
    """Trigger a Cloud Run Job via the Cloud Run Admin API.

    Uses Application Default Credentials — works in Cloud Run when the
    runtime service account has `roles/run.developer` (or a narrower
    role with `run.executions.create`).

    Returns the execution name (short form) on success. Raises
    `requests.HTTPError` on non-2xx and `google.auth.exceptions.GoogleAuthError`
    if credentials can't be obtained.
    """
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    url = _CLOUD_RUN_JOBS_API.format(project=project, region=region, job=job_name)
    resp = http_requests.post(
        url,
        headers={"Authorization": f"Bearer {credentials.token}"},
        json={},
        timeout=15,
    )
    resp.raise_for_status()
    execution_name = resp.json().get("name", "").split("/")[-1]
    logger.info(
        "Cloud Run Job triggered.",
        extra={"job": job_name, "execution": execution_name},
    )
    return execution_name


# --- GOOGLE SHEETS ---


def get_sheets_data(service, spreadsheet_id) -> list[dict]:
    """Reads and processes all sheets from a Google Spreadsheet."""
    sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    sheets = sheet_metadata.get("sheets", "")

    all_leagues_data = []
    for sheet in sheets:
        sheet_title = sheet.get("properties", {}).get("title", "Sin Título")
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=sheet_title)
            .execute()
        )
        values = result.get("values", [])

        if not values or len(values) < 6:
            continue

        league_info = {
            "nombre": values[0][1] if len(values[0]) > 1 else "N/A",
            "descripcion": values[1][1] if len(values[1]) > 1 else "N/A",
            "premio": values[2][1] if len(values[2]) > 1 else "N/A",
            "headers": values[4],
            "rows": values[5:],
        }
        all_leagues_data.append(league_info)
    return all_leagues_data
