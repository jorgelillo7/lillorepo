import google.auth
import google.auth.transport.requests
import requests as http_requests

from core.utils import get_logger

logger = get_logger(__name__)


def trigger_analyzer_job(project: str, region: str, job_name: str) -> None:
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    url = (
        f"https://{region}-run.googleapis.com/apis/run.googleapis.com/v1"
        f"/namespaces/{project}/jobs/{job_name}:run"
    )
    resp = http_requests.post(url, headers={"Authorization": f"Bearer {creds.token}"})
    resp.raise_for_status()
    logger.info("Cloud Run Job triggered", extra={"job": job_name})
