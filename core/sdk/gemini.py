"""Minimal Gemini API client — REST via `requests`, no SDK.

Deliberate: the google-genai SDK would add a dependency (and a python-base
image rebuild) for what is a single POST. Same philosophy as
`core/sdk/biwenger.py`. Structured output via `responseSchema` guarantees
parseable JSON back.
"""

import base64
import json

import requests

from core.utils import get_logger

logger = get_logger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# The `-latest` alias tracks the current flash generation — pinned versions
# get retired for new API keys (gemini-2.5-flash already 404s on ours).
DEFAULT_MODEL = "gemini-flash-latest"
# No `-latest` alias exists for image models; callers should treat failures
# as degradable (and override via env when this one gets retired too).
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"


class GeminiError(Exception):
    """API refusal, empty candidates or unparseable response."""


def generate_json(
    api_key: str,
    prompt: str,
    image_bytes: bytes | None = None,
    image_mime: str = "image/jpeg",
    schema: dict | None = None,
    model: str = DEFAULT_MODEL,
    timeout: int = 45,
) -> dict:
    """One-shot structured generation: prompt (+ optional image) → dict.

    Raises `GeminiError` on API errors or malformed output; network errors
    propagate as `requests.RequestException` so callers can distinguish
    "Gemini said no" from "the wire broke".
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

    response = requests.post(
        f"{GEMINI_API_BASE}/models/{model}:generateContent",
        params={"key": api_key},
        json={
            "contents": [{"parts": parts}],
            "generationConfig": generation_config,
        },
        timeout=timeout,
    )
    if response.status_code != 200:
        raise GeminiError(f"Gemini HTTP {response.status_code}: {response.text[:200]}")
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
) -> bytes:
    """Image-editing call: prompt + source image → edited image bytes.

    Same error contract as `generate_json`."""
    response = requests.post(
        f"{GEMINI_API_BASE}/models/{model}:generateContent",
        params={"key": api_key},
        json={
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
        timeout=timeout,
    )
    if response.status_code != 200:
        raise GeminiError(f"Gemini HTTP {response.status_code}: {response.text[:200]}")
    try:
        parts = response.json()["candidates"][0]["content"]["parts"]
        for part in parts:
            blob = part.get("inlineData") or part.get("inline_data")
            if blob and blob.get("data"):
                return base64.b64decode(blob["data"])
        raise KeyError("no image part in response")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GeminiError(f"Unparseable Gemini image response: {exc}") from exc
