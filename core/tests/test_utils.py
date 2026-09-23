import pytest

from core import utils


def test_read_secret_from_file_exists(mock_filesystem):
    """Reads the content of an existing file."""
    secret_path = mock_filesystem("test_secret.txt", "my_secret_password")
    assert utils.read_secret_from_file(secret_path) == "my_secret_password"


def test_read_secret_from_file_not_exists():
    """Returns the fallback when the file does not exist."""
    assert utils.read_secret_from_file("/nonexistent/path", "default") == "default"


def test_read_secret_from_file_empty_path():
    """Returns the fallback when the path is empty."""
    assert utils.read_secret_from_file("", "default") == "default"


def test_load_json_secret_parses_an_object(monkeypatch):
    monkeypatch.setenv("SOME_SECRET_JSON", '{"email": "a@b.c"}')
    assert utils.load_json_secret("SOME_SECRET_JSON") == {"email": "a@b.c"}


def test_load_json_secret_missing_or_empty_is_an_empty_config(monkeypatch):
    """Local dev and tests run without the secret and fall back to individual
    env vars, so an absent secret is a normal state, not an error."""
    monkeypatch.delenv("SOME_SECRET_JSON", raising=False)
    assert utils.load_json_secret("SOME_SECRET_JSON") == {}
    monkeypatch.setenv("SOME_SECRET_JSON", "  ")
    assert utils.load_json_secret("SOME_SECRET_JSON") == {}


def test_load_json_secret_malformed_raises_naming_the_variable(monkeypatch):
    """A corrupted secret in production used to read as `{}`: the credentials
    fell back to empty strings and the failure surfaced later as a login error,
    far from its cause. The message names the variable and never the value."""
    monkeypatch.setenv("SOME_SECRET_JSON", '{"password": "hunter2"')
    with pytest.raises(ValueError, match="SOME_SECRET_JSON") as caught:
        utils.load_json_secret("SOME_SECRET_JSON")
    assert "hunter2" not in str(caught.value)


def test_load_json_secret_that_is_not_an_object_raises(monkeypatch):
    """Every caller chains `.get(...)` on the result."""
    monkeypatch.setenv("SOME_SECRET_JSON", '["a", "b"]')
    with pytest.raises(ValueError, match="SOME_SECRET_JSON"):
        utils.load_json_secret("SOME_SECRET_JSON")
