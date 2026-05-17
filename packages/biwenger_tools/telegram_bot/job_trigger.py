import google.auth
import google.auth.exceptions
import google.auth.transport.requests
import requests as http_requests

from core.utils import get_logger

logger = get_logger(__name__)


def get_job_update_time(project: str, region: str, job_name: str) -> str | None:
    """Return the updateTime of the Cloud Run Job's current state.

    Used by `/version` to report when the analyzer job was last redeployed.
    Returns the raw RFC3339 timestamp from the API, or `None` if the lookup
    fails (auth, transient network errors, job missing).
    """
    try:
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        url = (
            f"https://run.googleapis.com/v2/projects/{project}"
            f"/locations/{region}/jobs/{job_name}"
        )
        resp = http_requests.get(
            url,
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("updateTime")
    except (
        google.auth.exceptions.GoogleAuthError,
        http_requests.RequestException,
    ) as exc:
        logger.warning("Failed to fetch job updateTime.", extra={"error": str(exc)})
        return None


def trigger_analyzer_job(
    project: str, region: str, job_name: str, mode: str = "daily"
) -> None:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    url = (
        f"https://{region}-run.googleapis.com/apis/run.googleapis.com/v1"
        f"/namespaces/{project}/jobs/{job_name}:run"
    )
    body = {
        "overrides": {
            "containerOverrides": [{"env": [{"name": "ANALYSIS_MODE", "value": mode}]}]
        }
    }
    resp = http_requests.post(
        url,
        json=body,
        headers={"Authorization": f"Bearer {creds.token}"},
    )
    resp.raise_for_status()
    logger.info("Cloud Run Job triggered", extra={"job": job_name, "mode": mode})
