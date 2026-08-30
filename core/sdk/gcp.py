import json
import uuid
from urllib.parse import quote

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


# --- CLOUD STORAGE ---
#
# The JSON API over ADC rather than `google-cloud-storage`: the library is not
# in the lock file and pulling it in for two calls would drag a dependency bump
# (and a python-base rebuild) into a feature change.

_GCS_UPLOAD_URL = "https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
_GCS_OBJECT_URL = "https://storage.googleapis.com/storage/v1/b/{bucket}/o/{name}"
_GCS_PUBLIC_URL = "https://storage.googleapis.com/{bucket}/{name}"


def _gcs_token() -> str:
    """Bearer token for the storage scope from Application Default Credentials."""
    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/devstorage.read_write"]
    )
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


def upload_object(
    bucket: str,
    name: str,
    data: bytes,
    content_type: str,
    cache_control: str | None = None,
    timeout: int = 60,
) -> str:
    """Upload bytes to `gs://{bucket}/{name}`, overwriting. Returns the public URL.

    Sent as a `multipart` upload because that is the only single-request form
    that carries object metadata: with `uploadType=media` the API takes the
    bytes and the content type and **silently ignores** a `Cache-Control`
    request header, leaving the object on the bucket default of an hour.

    `cache_control` is worth setting on anything that changes in place — a
    public object that keeps the default keeps serving its old body from the
    edge long after it was overwritten.

    Raises `requests.HTTPError` on non-2xx (a 403 here means the runtime service
    account lacks `storage.objects.create` on the bucket) and
    `google.auth.exceptions.GoogleAuthError` if credentials can't be obtained.
    """
    metadata: dict[str, str] = {"name": name}
    if cache_control:
        metadata["cacheControl"] = cache_control

    boundary = f"lillorepo-{uuid.uuid4().hex}"
    body = b"".join(
        [
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n".encode(),
            json.dumps(metadata).encode("utf-8"),
            f"\r\n--{boundary}\r\nContent-Type: {content_type}\r\n\r\n".encode(),
            data,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    resp = http_requests.post(
        _GCS_UPLOAD_URL.format(bucket=bucket),
        params={"uploadType": "multipart"},
        headers={
            "Authorization": f"Bearer {_gcs_token()}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
        data=body,
        timeout=timeout,
    )
    resp.raise_for_status()
    logger.info(
        "Object uploaded to GCS.",
        extra={"bucket": bucket, "object": name, "bytes": len(data)},
    )
    return _GCS_PUBLIC_URL.format(bucket=bucket, name=quote(name, safe="/"))


def download_object(bucket: str, name: str, timeout: int = 30) -> bytes | None:
    """Read `gs://{bucket}/{name}`, or None if it does not exist.

    Authenticated and `no-cache` on purpose: a read-modify-write that merges
    onto a cached copy silently drops whatever was written since. A public
    object is cacheable by its content, so an `Authorization` header alone does
    not guarantee the current bytes.
    """
    resp = http_requests.get(
        _GCS_OBJECT_URL.format(bucket=bucket, name=quote(name, safe="")),
        params={"alt": "media"},
        headers={
            "Authorization": f"Bearer {_gcs_token()}",
            "Cache-Control": "no-cache",
        },
        timeout=timeout,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content


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
