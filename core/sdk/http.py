"""HTTP utilities shared by SDK clients.

Currently exposes `retry_http_request`: a single retry loop that wraps
calls against external APIs we don't own (Biwenger, JP, Telegram).

The retry policy is opinionated for this kind of caller:
- **Retried**: network errors (timeout, connection reset, DNS) and 5xx
  responses — the server might recover on the next attempt.
- **Fail-fast**: 4xx responses — they won't get better; the request is
  semantically wrong.

Why a shared helper instead of a library: keeps the dep footprint
small (we already use `requests`, no need for tenacity/backoff) and
gives every SDK the same observable behaviour in Cloud Logging.
"""

import time
from typing import Callable, Tuple

import requests

from core.utils import get_logger

logger = get_logger(__name__)

# Default backoff schedule (seconds). Three retries: roughly 2 + 5 + 10
# = 17 s of total wait, fits inside Cloud Run request budgets and the
# bot's 10 min api timeout. Override per-call when needed.
DEFAULT_BACKOFFS: Tuple[int, ...] = (2, 5, 10)


def retry_http_request(
    request_fn: Callable[[], requests.Response],
    *,
    label: str = "request",
    backoffs: Tuple[int, ...] = DEFAULT_BACKOFFS,
) -> requests.Response:
    """Run `request_fn` with backoff on transient failures.

    `request_fn` must return a `requests.Response` (or raise a
    `requests.RequestException`). The helper handles the retry loop and
    surfaces the final exception when all retries are exhausted.

    `label` is included in log messages so a Cloud Logging search by
    operation ("lineup PUT", "market bid POST") returns the right
    trail.
    """
    attempts = (0,) + tuple(backoffs)
    last_exc: requests.RequestException | None = None

    for attempt, backoff in enumerate(attempts, start=1):
        if backoff:
            logger.warning(
                "%s transient failure — retrying.",
                label,
                extra={
                    "label": label,
                    "attempt": attempt,
                    "backoff_s": backoff,
                    "error": str(last_exc) if last_exc else "",
                },
            )
            time.sleep(backoff)

        try:
            response = request_fn()
        except requests.RequestException as exc:
            last_exc = exc
            continue

        if response.ok:
            if attempt > 1:
                logger.info(
                    "%s succeeded after retry.",
                    label,
                    extra={"label": label, "attempts": attempt},
                )
            return response

        # 4xx is terminal — the request is semantically wrong, retrying
        # won't fix it. Surface the HTTPError immediately.
        if 400 <= response.status_code < 500:
            logger.error(
                "%s returned non-retryable %d.",
                label,
                response.status_code,
                extra={
                    "label": label,
                    "status": response.status_code,
                    "body": response.text[:500],
                },
            )
            response.raise_for_status()

        # 5xx → record and try again.
        last_exc = requests.HTTPError(
            f"{label} HTTP {response.status_code}", response=response
        )
        logger.warning(
            "%s returned retryable %d.",
            label,
            response.status_code,
            extra={
                "label": label,
                "status": response.status_code,
                "body": response.text[:500],
            },
        )

    logger.error(
        "%s exhausted retries.",
        label,
        extra={
            "label": label,
            "attempts": len(attempts),
            "error": str(last_exc),
        },
    )
    assert last_exc is not None
    raise last_exc
