"""Minimal Gemini API client — REST via `requests`, no SDK.

Deliberate: the google-genai SDK would add a dependency (and a python-base
image rebuild) for what is a single POST. Same philosophy as
`core/sdk/biwenger.py`. Structured output via `responseSchema` guarantees
parseable JSON back.
"""

import base64
import json
import time

import requests

from core.utils import get_logger

logger = get_logger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Pinned, not `-latest`: the alias read-timed out at 60 s for a whole morning
# and there is no way to tell which model is behind it — for a label reader
# that means the extraction changing without notice under a catalog people
# trust for being verified.
#
# **Measure with the production key.** Models are retired per key: a local
# `.env` key can be older and still reach a model production 404s on, and
# testing with the wrong one is how `gemini-2.5-flash` briefly got pinned here
# while production could not call it at all. Google names the replacement in
# the 404 body, which is how this value was found.
#
#     gcloud secrets versions access latest --secret=flask-web-config-regional \
#       --project=be-water-app
DEFAULT_MODEL = "gemini-3.6-flash"
# No `-latest` alias exists for image models; callers should treat failures
# as degradable (and override via env when this one gets retired too). Measured
# with the production key, as the note above demands: its predecessor answered
# 503 "experiencing high demand" through every retry while this one returned
# first time.
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image"

_RETRYABLE_STATUS = {429, 503}
_RETRY_BACKOFF_SECONDS = 2


class GeminiError(Exception):
    """API refusal, empty candidates or unparseable response."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _post_with_retry(
    url: str,
    api_key: str,
    payload: dict,
    timeout: int,
    retries: int,
    fallback_api_key: str = "",
) -> requests.Response:
    """POST, resending on a 429/503 (transient overload) up to `retries` times.

    A 429 that survives the retries is a quota wall, not a busy minute. When
    `fallback_api_key` is set the request is sent once more with it: the tier
    is a property of the key's project, so a key whose project has billing
    answers where the free one is out of allowance. Free first, paid only when
    free has nothing left — nothing is charged while the free quota holds.
    """
    response = requests.post(
        url, params={"key": api_key}, json=payload, timeout=timeout
    )
    for _ in range(retries):
        if response.status_code not in _RETRYABLE_STATUS:
            break
        time.sleep(_RETRY_BACKOFF_SECONDS)
        response = requests.post(
            url, params={"key": api_key}, json=payload, timeout=timeout
        )
    if response.status_code == 429 and fallback_api_key:
        # Logged loudly: this line is the only warning that the project just
        # started spending money.
        logger.warning("Free-tier quota exhausted — retrying on the paid key.")
        response = requests.post(
            url, params={"key": fallback_api_key}, json=payload, timeout=timeout
        )
    return response


def generate_json(
    api_key: str,
    prompt: str,
    image_bytes: bytes | None = None,
    image_mime: str = "image/jpeg",
    schema: dict | None = None,
    model: str = DEFAULT_MODEL,
    timeout: int = 45,
    retries: int = 0,
    fallback_api_key: str = "",
) -> dict:
    """One-shot structured generation: prompt (+ optional image) → dict.

    Raises `GeminiError` on API errors or malformed output; network errors
    propagate as `requests.RequestException` so callers can distinguish
    "Gemini said no" from "the wire broke". `retries` resends the request
    on a 429/503 (transient overload) before giving up — 0 by default so
    existing callers keep their current latency. `fallback_api_key`, when set,
    gets one last attempt on a 429 the retries could not clear: see
    `_post_with_retry`.
    """
    parts: list[dict] = [{"text": prompt}]
    if image_bytes is not None:
        parts.append(
            {
                "inline_data": {
                    "mime_type": image_mime,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }
        )
    generation_config: dict = {"responseMimeType": "application/json"}
    if schema is not None:
        generation_config["responseSchema"] = schema

    response = _post_with_retry(
        f"{GEMINI_API_BASE}/models/{model}:generateContent",
        api_key,
        {"contents": [{"parts": parts}], "generationConfig": generation_config},
        timeout,
        retries,
        fallback_api_key,
    )
    if response.status_code != 200:
        raise GeminiError(
            f"Gemini HTTP {response.status_code}: {response.text[:200]}",
            status_code=response.status_code,
        )
    try:
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise GeminiError(f"Unparseable Gemini response: {exc}") from exc


def generate_image(
    api_key: str,
    prompt: str,
    image_bytes: bytes,
    image_mime: str = "image/jpeg",
    model: str = DEFAULT_IMAGE_MODEL,
    timeout: int = 90,
    retries: int = 0,
    fallback_api_key: str = "",
) -> bytes:
    """Image-editing call: prompt + source image → edited image bytes.

    Same error contract as `generate_json`, and the same paid-key fallback —
    which matters most here: image generation carries the smallest free
    allowance of the two, so it is the call that runs out first."""
    response = _post_with_retry(
        f"{GEMINI_API_BASE}/models/{model}:generateContent",
        api_key,
        {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": image_mime,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        },
        timeout,
        retries,
        fallback_api_key,
    )
    if response.status_code != 200:
        raise GeminiError(
            f"Gemini HTTP {response.status_code}: {response.text[:200]}",
            status_code=response.status_code,
        )
    try:
        data = response.json()
        candidate = (data.get("candidates") or [{}])[0]
        content = candidate.get("content")
        if content is None:
            # HTTP 200 with no content = safety/recitation block or an empty
            # generation. Surface finishReason instead of a bare KeyError so
            # the log says *why* the image never came back.
            raise GeminiError(
                "Gemini returned no image "
                f"(finishReason={candidate.get('finishReason')!r}, "
                f"promptFeedback={data.get('promptFeedback')!r})"
            )
        for part in content["parts"]:
            blob = part.get("inlineData") or part.get("inline_data")
            if blob and blob.get("data"):
                return base64.b64decode(blob["data"])
        raise GeminiError(
            "Gemini returned no image part "
            f"(finishReason={candidate.get('finishReason')!r})"
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GeminiError(f"Unparseable Gemini image response: {exc}") from exc
