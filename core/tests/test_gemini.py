"""Unit tests for the minimal Gemini REST client."""

import base64
import json
from unittest.mock import patch

import pytest
import requests_mock

from core.sdk import gemini

_URL = f"{gemini.GEMINI_API_BASE}/models/{gemini.DEFAULT_MODEL}:generateContent"


def _api_response(payload: dict) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}


def test_generate_json_parses_structured_output():
    with requests_mock.Mocker() as m:
        m.post(_URL, json=_api_response({"tds": 261, "name": "Solán"}))
        result = gemini.generate_json("key", "parse this")
    assert result == {"tds": 261, "name": "Solán"}


def test_generate_json_sends_image_and_schema():
    with requests_mock.Mocker() as m:
        m.post(_URL, json=_api_response({}))
        gemini.generate_json(
            "key",
            "prompt",
            image_bytes=b"fake-jpeg",
            schema={"type": "OBJECT"},
        )
        body = m.last_request.json()
    parts = body["contents"][0]["parts"]
    assert parts[0] == {"text": "prompt"}
    assert parts[1]["inline_data"]["data"] == base64.b64encode(b"fake-jpeg").decode()
    assert body["generationConfig"]["responseSchema"] == {"type": "OBJECT"}
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_generate_json_raises_on_http_error():
    with requests_mock.Mocker() as m:
        m.post(_URL, status_code=429, text="quota")
        with pytest.raises(gemini.GeminiError, match="429"):
            gemini.generate_json("key", "prompt")


def test_generate_json_retries_on_503_then_succeeds():
    with requests_mock.Mocker() as m:
        m.post(
            _URL,
            [
                {"status_code": 503, "text": "overloaded"},
                {"json": _api_response({"name": "Bezoya"})},
            ],
        )
        with patch("core.sdk.gemini.time.sleep") as mock_sleep:
            result = gemini.generate_json("key", "prompt", retries=1)
    assert result == {"name": "Bezoya"}
    assert m.call_count == 2
    mock_sleep.assert_called_once_with(gemini._RETRY_BACKOFF_SECONDS)


def test_generate_json_raises_after_exhausting_retries():
    with requests_mock.Mocker() as m:
        m.post(_URL, status_code=503, text="overloaded")
        with patch("core.sdk.gemini.time.sleep"):
            with pytest.raises(gemini.GeminiError, match="503"):
                gemini.generate_json("key", "prompt", retries=1)
    assert m.call_count == 2


def test_generate_json_does_not_retry_by_default():
    with requests_mock.Mocker() as m:
        m.post(_URL, status_code=503, text="overloaded")
        with pytest.raises(gemini.GeminiError, match="503"):
            gemini.generate_json("key", "prompt")
    assert m.call_count == 1


def test_generate_json_raises_on_malformed_body():
    with requests_mock.Mocker() as m:
        m.post(_URL, json={"candidates": []})
        with pytest.raises(gemini.GeminiError, match="Unparseable"):
            gemini.generate_json("key", "prompt")


_IMG_URL = (
    f"{gemini.GEMINI_API_BASE}/models/{gemini.DEFAULT_IMAGE_MODEL}:generateContent"
)


def test_generate_image_decodes_inline_data():
    fake_png = b"\x89PNG-fake"
    body = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "here you go"},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": base64.b64encode(fake_png).decode(),
                            }
                        },
                    ]
                }
            }
        ]
    }
    with requests_mock.Mocker() as m:
        m.post(_IMG_URL, json=body)
        result = gemini.generate_image("key", "isolate", b"src")
        sent = m.last_request.json()
    assert result == fake_png
    assert sent["generationConfig"]["responseModalities"] == ["IMAGE"]


def test_generate_image_raises_without_image_part():
    with requests_mock.Mocker() as m:
        m.post(
            _IMG_URL, json={"candidates": [{"content": {"parts": [{"text": "no"}]}}]}
        )
        with pytest.raises(gemini.GeminiError, match="Unparseable"):
            gemini.generate_image("key", "isolate", b"src")
