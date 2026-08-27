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

    Used for the Google Sheets reader behind the competitions page. The
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


def get_workbook(service, spreadsheet_id) -> list[tuple[str, list[list[str]]]]:
    """Every tab of a spreadsheet as ``(title, rows)``, in the owner's order.

    Two API calls whatever the tab count: one for the metadata, one
    ``values.batchGet`` for all the ranges. The obvious loop is one call per
    tab, which does not scale to a workbook the league keeps adding
    competitions to.

    Rows come back ragged — the API truncates each at its last non-empty cell
    — and tabs are returned untouched. Deciding what a tab *is* belongs to the
    caller, which can then report what it ignored; the reader this replaced
    imposed a nombre/descripción/premio shape here and dropped any tab under
    six rows in silence.
    """
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [
        sheet.get("properties", {}).get("title", "")
        for sheet in metadata.get("sheets", [])
    ]
    titles = [t for t in titles if t]
    if not titles:
        return []

    # Quoted so a tab called "Copa Castolo" is one range, not a parse error.
    batch = (
        service.spreadsheets()
        .values()
        .batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=[f"'{t}'" for t in titles],
        )
        .execute()
    )
    ranges = batch.get("valueRanges", [])
    return [
        (title, ranges[i].get("values", []) if i < len(ranges) else [])
        for i, title in enumerate(titles)
    ]
