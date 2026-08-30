import json
from unittest.mock import MagicMock
from urllib.parse import quote

import pytest
import requests
import requests_mock

from core.sdk import gcp

# --- Google Sheets ---


def _service_with(tabs):
    """A Sheets client whose workbook has `tabs` = {title: rows}."""
    service = MagicMock()
    spreadsheets = service.spreadsheets.return_value
    spreadsheets.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": t}} for t in tabs]
    }
    spreadsheets.values.return_value.batchGet.return_value.execute.return_value = {
        "valueRanges": [{"values": rows} for rows in tabs.values()]
    }
    return service, spreadsheets


def test_get_workbook_reads_every_tab_in_two_calls():
    """One metadata call plus one batchGet, whatever the tab count. The loop
    it replaced was one call per tab, which does not scale to a workbook the
    league keeps adding competitions to."""
    service, spreadsheets = _service_with(
        {"Hoja3": [["Jornada", "Partido"]], "Copa Castolo": [["Equipo", "J1"]]}
    )

    result = gcp.get_workbook(service, "spreadsheet_id")

    assert result == [
        ("Hoja3", [["Jornada", "Partido"]]),
        ("Copa Castolo", [["Equipo", "J1"]]),
    ]
    assert spreadsheets.values.return_value.batchGet.call_count == 1
    # Tab titles are quoted, or "Copa Castolo" parses as two ranges.
    ranges = spreadsheets.values.return_value.batchGet.call_args.kwargs["ranges"]
    assert ranges == ["'Hoja3'", "'Copa Castolo'"]


def test_get_workbook_returns_empty_tabs_as_empty():
    """A tab created and not filled in comes back with no values, and must
    not shift the tabs after it."""
    service, spreadsheets = _service_with({"Vacia": [], "Llena": [["a"]]})
    spreadsheets.values.return_value.batchGet.return_value.execute.return_value = {
        "valueRanges": [{}, {"values": [["a"]]}]
    }

    assert gcp.get_workbook(service, "x") == [("Vacia", []), ("Llena", [["a"]])]


def test_get_workbook_with_no_tabs_makes_no_values_call():
    """No tabs means no ranges to ask for — an empty batchGet is an error."""
    service, spreadsheets = _service_with({})

    assert gcp.get_workbook(service, "x") == []
    spreadsheets.values.return_value.batchGet.assert_not_called()


# --- Cloud Storage ---


def _patched_token(monkeypatch):
    monkeypatch.setattr(gcp, "_gcs_token", lambda: "tok")


def _multipart_parts(body: bytes) -> tuple[dict, bytes]:
    """`(metadata, payload)` out of a multipart/related upload body."""
    boundary = body.split(b"\r\n", 1)[0]
    sections = [p for p in body.split(boundary) if b"Content-Type" in p]
    metadata = json.loads(sections[0].split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n"))
    payload = sections[1].split(b"\r\n\r\n", 1)[1].rstrip(b"\r\n")
    return metadata, payload


def test_upload_object_sends_cache_control_as_object_metadata(monkeypatch):
    """As a metadata part, not a request header: `uploadType=media` accepts the
    header and silently drops it, leaving the object on the bucket default of
    an hour — which is how a replaced front page kept serving the old scan."""
    _patched_token(monkeypatch)
    with requests_mock.Mocker() as m:
        m.post(gcp._GCS_UPLOAD_URL.format(bucket="biwenger"), json={"name": "x"})

        url = gcp.upload_object(
            "biwenger",
            "periodico/26-27/index.json",
            b"[]",
            "application/json",
            cache_control="public, max-age=60",
        )

    assert url == "https://storage.googleapis.com/biwenger/periodico/26-27/index.json"
    request = m.last_request
    assert request.qs == {"uploadtype": ["multipart"]}
    assert request.headers["Authorization"] == "Bearer tok"
    assert request.headers["Content-Type"].startswith("multipart/related; boundary=")

    metadata, payload = _multipart_parts(request.body)
    assert metadata == {
        "name": "periodico/26-27/index.json",
        "cacheControl": "public, max-age=60",
    }
    assert payload == b"[]"


def test_upload_object_omits_cache_control_when_not_given(monkeypatch):
    _patched_token(monkeypatch)
    with requests_mock.Mocker() as m:
        m.post(gcp._GCS_UPLOAD_URL.format(bucket="b"), json={})

        gcp.upload_object(
            "b", "periodico/26-27/2026-08-14.jpg", b"\xff\xd8\xff", "image/jpeg"
        )

    metadata, payload = _multipart_parts(m.last_request.body)
    assert metadata == {"name": "periodico/26-27/2026-08-14.jpg"}
    assert payload == b"\xff\xd8\xff"


def test_upload_object_raises_on_denied_write(monkeypatch):
    """A 403 means the runtime service account cannot write the bucket — it has
    to surface, not be swallowed into a silent no-op."""
    _patched_token(monkeypatch)
    with requests_mock.Mocker() as m:
        m.post(gcp._GCS_UPLOAD_URL.format(bucket="b"), status_code=403, json={})

        with pytest.raises(requests.HTTPError):
            gcp.upload_object("b", "n", b"x", "image/jpeg")


def test_download_object_returns_bytes(monkeypatch):
    _patched_token(monkeypatch)
    name = quote("periodico/26-27/index.json", safe="")
    with requests_mock.Mocker() as m:
        m.get(
            gcp._GCS_OBJECT_URL.format(bucket="b", name=name),
            content=b'[{"fecha": "2026-08-14"}]',
        )

        assert gcp.download_object("b", "periodico/26-27/index.json") == (
            b'[{"fecha": "2026-08-14"}]'
        )
    assert m.last_request.qs["alt"] == ["media"]
    assert m.last_request.headers["Authorization"] == "Bearer tok"
    # A public object is cacheable by its content, so the read has to say so
    # explicitly or a read-modify-write can merge onto a stale copy.
    assert m.last_request.headers["Cache-Control"] == "no-cache"


def test_download_object_returns_none_when_missing(monkeypatch):
    """A season that has published nothing yet has no manifest — that is the
    normal first write, not a failure."""
    _patched_token(monkeypatch)
    with requests_mock.Mocker() as m:
        m.get(gcp._GCS_OBJECT_URL.format(bucket="b", name="missing"), status_code=404)

        assert gcp.download_object("b", "missing") is None
