"""Tests for `core.sdk.http.retry_http_request`."""

from unittest.mock import MagicMock

import pytest
import requests

from core.sdk.http import retry_http_request


def _resp(status: int = 200, body: str = "ok"):
    r = requests.Response()
    r.status_code = status
    r._content = body.encode()
    return r


def test_returns_immediately_on_first_success():
    fn = MagicMock(return_value=_resp(200))
    response = retry_http_request(fn, label="t", backoffs=(0, 0))
    assert response.status_code == 200
    assert fn.call_count == 1  # no retry on success


def test_fail_fast_on_4xx_without_retrying():
    """4xx is the caller's mistake — retrying never helps. Raise immediately."""
    fn = MagicMock(return_value=_resp(400, "bad request"))
    with pytest.raises(requests.HTTPError):
        retry_http_request(fn, label="t", backoffs=(0, 0))
    assert fn.call_count == 1


def test_retries_on_5xx_then_succeeds():
    """5xx is retryable — server may recover."""
    fn = MagicMock(side_effect=[_resp(503), _resp(200)])
    response = retry_http_request(fn, label="t", backoffs=(0,))
    assert response.status_code == 200
    assert fn.call_count == 2


def test_retries_on_network_error_then_succeeds():
    fn = MagicMock(
        side_effect=[requests.ConnectionError("boom"), _resp(200)],
    )
    response = retry_http_request(fn, label="t", backoffs=(0,))
    assert response.status_code == 200
    assert fn.call_count == 2


def test_raises_after_exhausted_retries_on_persistent_5xx():
    fn = MagicMock(return_value=_resp(500, "boom"))
    with pytest.raises(requests.HTTPError):
        retry_http_request(fn, label="t", backoffs=(0, 0))
    assert fn.call_count == 3  # initial + 2 retries


def test_raises_after_exhausted_retries_on_persistent_network_error():
    err = requests.Timeout("slow")
    fn = MagicMock(side_effect=err)
    with pytest.raises(requests.Timeout):
        retry_http_request(fn, label="t", backoffs=(0, 0))
    assert fn.call_count == 3


def test_label_appears_in_logs(caplog):
    """The `label` arg is what makes Cloud Logging searchable per operation."""
    import logging

    caplog.set_level(logging.WARNING)
    fn = MagicMock(side_effect=[_resp(503), _resp(200)])
    retry_http_request(fn, label="lineup PUT", backoffs=(0,))
    assert any("lineup PUT" in r.message for r in caplog.records)
