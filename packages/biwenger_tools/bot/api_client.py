"""HTTP client that talks to biwenger-api with a Google-signed ID token.

The bot used to enqueue Cloud Run Jobs to run analyzer modes. After PR 3,
modes are real HTTP endpoints on `biwenger-api`. This module wraps the
requests + auth boilerplate so `app.py` only sees `call_api(path, method)`.
"""

import google.auth
import google.auth.exceptions
import google.auth.transport.requests
import google.oauth2.id_token
import requests as http_requests

from core.utils import get_logger

logger = get_logger(__name__)


def _fetch_id_token(audience: str) -> str:
    """Return a Google-signed ID token for the given audience.

    On Cloud Run, this works via the metadata server with no extra config —
    the runtime SA's identity is used. Locally, falls back to ADC.
    """
    auth_req = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(auth_req, audience)


def call_api(
    base_url: str,
    path: str,
    method: str = "POST",
    timeout: int = 600,
    params: dict | None = None,
) -> None:
    """Call biwenger-api with an ID token. Raises on non-2xx.

    Timeout is generous (10 min default) because the api endpoints do real
    work synchronously: fetch JP, fetch Biwenger, render PNGs, send to
    Telegram. Cloud Run caps requests at 60 min by default; 10 min is a
    comfortable upper bound for these handlers.
    """
    url = base_url.rstrip("/") + path
    token = _fetch_id_token(base_url)
    resp = http_requests.request(
        method,
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params=params,
        json={} if method != "GET" else None,
        timeout=timeout,
    )
    resp.raise_for_status()
    logger.info(
        "biwenger-api call ok.",
        extra={"path": path, "method": method, "status": resp.status_code},
    )


def list_managers(base_url: str, timeout: int = 30) -> list[dict] | None:
    """Fetch the league managers — used by the bot's /analizar picker.

    Returns a list of `{id, name, is_me}` or None on failure. Short
    timeout: the api endpoint hits Biwenger's `league` endpoint once and
    returns plain JSON, no images.
    """
    url = base_url.rstrip("/") + "/managers"
    try:
        token = _fetch_id_token(base_url)
        resp = http_requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("managers", [])
    except (
        google.auth.exceptions.GoogleAuthError,
        http_requests.RequestException,
        ValueError,
    ) as exc:
        logger.warning("Failed to fetch managers.", extra={"error": str(exc)})
        return None


def get_api_version(base_url: str, timeout: int = 10) -> dict | None:
    """Fetch /version from biwenger-api. Returns None on failure."""
    url = base_url.rstrip("/") + "/version"
    try:
        token = _fetch_id_token(base_url)
        resp = http_requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except (
        google.auth.exceptions.GoogleAuthError,
        http_requests.RequestException,
        ValueError,
    ) as exc:
        logger.warning(
            "Failed to fetch biwenger-api /version.", extra={"error": str(exc)}
        )
        return None
