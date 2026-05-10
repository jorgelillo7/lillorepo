"""Tests for the Telegram bot webhook."""

import pytest
from unittest.mock import patch

import packages.biwenger_tools.telegram_bot.config as cfg
from packages.biwenger_tools.telegram_bot.app import app

_VALID_SECRET = "test-secret"
_VALID_CHAT = "111222333"


@pytest.fixture(autouse=True)
def patch_config():
    """Set known config values for every test."""
    cfg.TELEGRAM_WEBHOOK_SECRET = _VALID_SECRET
    cfg.TELEGRAM_CHAT_ID = _VALID_CHAT
    cfg.TELEGRAM_BOT_TOKEN = "test-token"
    cfg.GCP_PROJECT_ID = "test-project"
    cfg.CLOUD_RUN_REGION = "us-central1"
    cfg.CLOUD_RUN_JOB_NAME = "test-job"
    yield


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _update(chat_id, text):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


def _post(client, body, secret=_VALID_SECRET):
    return client.post(
        "/telegram/webhook",
        json=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": secret},
    )


# --- Auth ---


def test_wrong_secret_returns_401(client):
    resp = _post(client, _update(_VALID_CHAT, "/analizar"), secret="wrong")
    assert resp.status_code == 401


def test_correct_secret_returns_200(client):
    trigger = (
        "packages.biwenger_tools.telegram_bot.app.job_trigger.trigger_analyzer_job"
    )
    with patch(trigger):
        resp = _post(client, _update(_VALID_CHAT, "/analizar"))
    assert resp.status_code == 200


# --- Chat filter ---


def test_wrong_chat_id_is_silently_ignored(client):
    with patch(
        "packages.biwenger_tools.telegram_bot.app.job_trigger.trigger_analyzer_job"
    ) as mock_trigger:
        resp = _post(client, _update("999999", "/analizar"))
    assert resp.status_code == 200
    mock_trigger.assert_not_called()


# --- Commands ---


def test_analizar_triggers_job_once(client):
    with patch(
        "packages.biwenger_tools.telegram_bot.app.job_trigger.trigger_analyzer_job"
    ) as mock_trigger:
        resp = _post(client, _update(_VALID_CHAT, "/analizar"))
    assert resp.status_code == 200
    mock_trigger.assert_called_once_with(
        "test-project", "us-central1", "test-job", mode="all"
    )


def test_myteam_triggers_job_with_mode(client):
    with patch(
        "packages.biwenger_tools.telegram_bot.app.job_trigger.trigger_analyzer_job"
    ) as mock_trigger:
        resp = _post(client, _update(_VALID_CHAT, "/myTeam"))
    assert resp.status_code == 200
    mock_trigger.assert_called_once_with(
        "test-project", "us-central1", "test-job", mode="my_team"
    )


def test_myteam_lowercase_from_menu_triggers_job(client):
    with patch(
        "packages.biwenger_tools.telegram_bot.app.job_trigger.trigger_analyzer_job"
    ) as mock_trigger:
        resp = _post(client, _update(_VALID_CHAT, "/myteam"))
    assert resp.status_code == 200
    mock_trigger.assert_called_once_with(
        "test-project", "us-central1", "test-job", mode="my_team"
    )


def test_mercado_triggers_job_with_mode(client):
    with patch(
        "packages.biwenger_tools.telegram_bot.app.job_trigger.trigger_analyzer_job"
    ) as mock_trigger:
        resp = _post(client, _update(_VALID_CHAT, "/mercado"))
    assert resp.status_code == 200
    mock_trigger.assert_called_once_with(
        "test-project", "us-central1", "test-job", mode="market"
    )


def test_alinear_triggers_job_with_mode(client):
    with patch(
        "packages.biwenger_tools.telegram_bot.app.job_trigger.trigger_analyzer_job"
    ) as mock_trigger:
        resp = _post(client, _update(_VALID_CHAT, "/alinear"))
    assert resp.status_code == 200
    mock_trigger.assert_called_once_with(
        "test-project", "us-central1", "test-job", mode="alinear"
    )


def test_help_sends_message(client):
    with patch(
        "packages.biwenger_tools.telegram_bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/help"))
    assert resp.status_code == 200
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs.get("chat_id") == _VALID_CHAT


def test_unknown_command_is_ignored(client):
    with patch(
        "packages.biwenger_tools.telegram_bot.app.job_trigger.trigger_analyzer_job"
    ) as mock_trigger, patch(
        "packages.biwenger_tools.telegram_bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/unknown"))
    assert resp.status_code == 200
    mock_trigger.assert_not_called()
    mock_send.assert_not_called()


def test_command_with_botname_suffix_triggers_job(client):
    with patch(
        "packages.biwenger_tools.telegram_bot.app.job_trigger.trigger_analyzer_job"
    ) as mock_trigger:
        resp = _post(client, _update(_VALID_CHAT, "/analizar@biwenger_tools_bot"))
    assert resp.status_code == 200
    mock_trigger.assert_called_once_with(
        "test-project", "us-central1", "test-job", mode="all"
    )


def test_job_trigger_failure_sends_error_message(client):
    with patch(
        "packages.biwenger_tools.telegram_bot.app.job_trigger.trigger_analyzer_job",
        side_effect=RuntimeError("permission denied"),
    ), patch(
        "packages.biwenger_tools.telegram_bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/analizar"))
    assert resp.status_code == 200
    # first call = ACK, second call = error
    assert mock_send.call_count == 2
    error_text = mock_send.call_args_list[1].kwargs.get("text", "")
    assert "permission denied" in error_text


def test_empty_body_does_not_crash(client):
    resp = client.post(
        "/telegram/webhook",
        data="",
        content_type="application/json",
        headers={"X-Telegram-Bot-Api-Secret-Token": _VALID_SECRET},
    )
    assert resp.status_code == 200
