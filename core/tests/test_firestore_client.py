"""Client construction for `core/sdk/firestore.py`, without the emulator.

`test_firestore_sdk.py` needs a running emulator and skips in CI; how the
client is built does not, so it is pinned here where CI runs it.
"""

from unittest.mock import MagicMock

import pytest

from core.sdk import firestore


@pytest.fixture(autouse=True)
def fresh_client(monkeypatch):
    monkeypatch.setattr(firestore, "_client", None)
    monkeypatch.delenv("FIRESTORE_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    client_class = MagicMock()
    monkeypatch.setattr(firestore.firestore, "Client", client_class)
    return client_class


def test_the_project_comes_from_the_environment_first(fresh_client, monkeypatch):
    """be_water deploys to its own project and says so through
    `FIRESTORE_PROJECT`; that has to win over `GOOGLE_CLOUD_PROJECT`."""
    monkeypatch.setenv("FIRESTORE_PROJECT", "be-water-app")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "biwenger-tools")
    firestore.get_client()
    fresh_client.assert_called_once_with(project="be-water-app")


def test_google_cloud_project_is_the_fallback(fresh_client, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "biwenger-tools")
    firestore.get_client()
    fresh_client.assert_called_once_with(project="biwenger-tools")


def test_with_no_project_set_the_credentials_decide(fresh_client):
    """Inside Cloud Run the ambient ADC credentials name the project."""
    firestore.get_client()
    fresh_client.assert_called_once_with()


def test_the_client_is_built_once_per_process(fresh_client):
    first = firestore.get_client()
    assert firestore.get_client() is first
    fresh_client.assert_called_once()
