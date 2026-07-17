"""Unit tests for the minimal Gemini REST client."""

import base64
import json

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


def test_generate_json_raises_on_malformed_body():
    with requests_mock.Mocker() as m:
        m.post(_URL, json={"candidates": []})
        with pytest.raises(gemini.GeminiError, match="Unparseable"):
            gemini.generate_json("key", "prompt")
