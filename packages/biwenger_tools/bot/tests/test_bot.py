"""Tests for the Biwenger bot webhook."""

import inspect
import re
import sys
from unittest.mock import patch

import pytest

import packages.biwenger_tools.bot.config as cfg
from packages.biwenger_tools.bot.menu import MAIN_MENU_ACTIONS
from packages.biwenger_tools.bot.app import app

_VALID_SECRET = "test-secret"
_VALID_CHAT = "111222333"
_VALID_DRAFT_CHAT = "444555666"
_API_URL = "https://biwenger-api.example.run.app"


@pytest.fixture(autouse=True)
def patch_config():
    """Set known config values for every test."""
    cfg.TELEGRAM_WEBHOOK_SECRET = _VALID_SECRET
    cfg.TELEGRAM_CHAT_ID = _VALID_CHAT
    cfg.TELEGRAM_DRAFT_CHAT_ID = _VALID_DRAFT_CHAT
    cfg.TELEGRAM_BOT_TOKEN = "test-token"
    cfg.BIWENGER_API_URL = _API_URL
    yield


@pytest.fixture(autouse=True)
def run_background_sync():
    """Force `_run_in_background` to run sync so the test thread sees the
    mocked api call before asserting. Production keeps the daemon-thread
    behaviour."""
    with patch(
        "packages.biwenger_tools.bot.app._run_in_background",
        side_effect=lambda fn, *a, **kw: fn(*a, **kw),
    ):
        yield


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _update(chat_id, text):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


def _group_update(chat_id, text, user_id):
    """Webhook body for a group text message — carries `from` (sender)."""
    return {
        "update_id": 1,
        "message": {
            "chat": {"id": chat_id},
            "text": text,
            "from": {"id": user_id},
        },
    }


def _service_message_update(chat_id):
    """Webhook body for a Telegram service message — no `text` at all."""
    return {
        "update_id": 1,
        "message": {"chat": {"id": chat_id}, "new_chat_member": {"id": 999}},
    }


def _callback_update(
    chat_id, data, message_id=42, query_id="cb-1", from_user_id=None, text=""
):
    """Webhook body for an inline-keyboard tap.

    `text` is the tapped message's body. Telegram always sends it and the
    offer flow writes its verdict on top of it, so it is worth being able to
    set here."""
    callback_query = {
        "id": query_id,
        "data": data,
        "message": {
            "chat": {"id": chat_id},
            "message_id": message_id,
            "text": text,
        },
    }
    if from_user_id is not None:
        callback_query["from"] = {"id": from_user_id}
    return {"update_id": 2, "callback_query": callback_query}


def _post(client, body, secret=_VALID_SECRET):
    return client.post(
        "/telegram/webhook",
        json=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": secret},
    )


# --- Auth ---


def test_wrong_secret_returns_401(client):
    resp = _post(client, _update(_VALID_CHAT, "/mercado"), secret="wrong")
    assert resp.status_code == 401


def test_correct_secret_returns_200(client):
    with patch("packages.biwenger_tools.bot.app.api_client.call_api"):
        resp = _post(client, _update(_VALID_CHAT, "/mercado"))
    assert resp.status_code == 200


# --- Chat filter ---


def test_wrong_chat_id_is_silently_ignored(client):
    with patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        resp = _post(client, _update("999999", "/mercado"))
    assert resp.status_code == 200
    mock_call.assert_not_called()


def test_wrong_chat_callback_is_silently_ignored(client):
    with patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        resp = _post(client, _callback_update("999999", "analizar:1"))
    assert resp.status_code == 200
    mock_call.assert_not_called()


# --- Direct text commands → api route mapping ---


@pytest.mark.parametrize(
    "command,path,method,params",
    [
        ("/mercado", "/market", "GET", None),
        ("/alinear", "/lineups/auto-pick", "POST", None),
        ("/preview", "/lineups/auto-pick", "POST", {"dry_run": "1"}),
        ("/recomendar", "/budget/recommendations", "GET", None),
        ("/pujar", "/market/auto-bid", "POST", None),
        ("/scrapper", "/scraper/trigger", "POST", None),
        ("/emergencia", "/emergency/clausulazo/preview", "POST", None),
        ("/ofertas", "/offers/inbox", "POST", None),
    ],
)
def test_text_command_calls_api(client, command, path, method, params):
    with patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        resp = _post(client, _update(_VALID_CHAT, command))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(_API_URL, path, method=method, params=params)


def test_command_with_botname_suffix_routes_correctly(client):
    with patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        resp = _post(client, _update(_VALID_CHAT, "/mercado@biwenger_tools_bot"))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(_API_URL, "/market", method="GET", params=None)


def test_preview_text_command_calls_api_with_dry_run(client):
    """`/preview` calls /lineups/auto-pick with `?dry_run=1`."""
    with patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        resp = _post(client, _update(_VALID_CHAT, "/preview"))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(
        _API_URL, "/lineups/auto-pick", method="POST", params={"dry_run": "1"}
    )


def test_api_call_failure_sends_error_message(client):
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api",
        side_effect=RuntimeError("permission denied"),
    ), patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/mercado"))
    assert resp.status_code == 200
    # first call = ACK, second call = error
    assert mock_send.call_count == 2
    error_text = mock_send.call_args_list[1].kwargs.get("text", "")
    assert "permission denied" in error_text


def test_api_call_failure_html_escapes_exception_message(client):
    """The error message embeds `exc` inside `<code>...</code>`. If `exc`
    itself contains `<` / `>` / `&` (e.g. an HTTP error body with markup),
    the second Telegram send would also 400 and the user would see
    nothing. Defensive escape keeps the failure path actionable."""
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api",
        side_effect=RuntimeError("500: <error>boom & boom</error>"),
    ), patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/pujar"))
    assert resp.status_code == 200
    error_text = mock_send.call_args_list[1].kwargs.get("text", "")
    # The exception text is escaped before landing in the body.
    assert "&lt;error&gt;boom &amp; boom&lt;/error&gt;" in error_text
    # The literal raw `<error>` substring must NOT leak through.
    assert "<error>" not in error_text


# --- /analizar opens the manager picker ---


def test_analizar_text_command_opens_manager_picker(client):
    """`/analizar` does NOT call /teams directly — it opens the picker."""
    fake_managers = [
        {"id": 1, "name": "Jorge", "is_me": True},
        {"id": 2, "name": "Pepe", "is_me": False},
    ]
    with patch(
        "packages.biwenger_tools.bot.app.api_client.list_managers",
        return_value=fake_managers,
    ), patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/analizar"))
    assert resp.status_code == 200
    mock_call.assert_not_called()
    # The picker message carries an inline keyboard with one row per manager
    # plus the TODOS row.
    markup = mock_send.call_args.kwargs.get("reply_markup")
    assert markup is not None
    rows = markup["inline_keyboard"]
    assert len(rows) == 3  # 2 managers + TODOS
    assert rows[-1][0]["callback_data"] == "analizar:all"


def test_analizar_text_command_handles_manager_fetch_failure(client):
    """If `/managers` is unreachable, the bot tells the user instead of
    sending an empty keyboard."""
    with patch(
        "packages.biwenger_tools.bot.app.api_client.list_managers",
        return_value=None,
    ), patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/analizar"))
    assert resp.status_code == 200
    text = mock_send.call_args.kwargs.get("text", "")
    assert "No pude cargar la lista" in text


# --- /menu attaches the persistent reply keyboard ---


def test_menu_sends_persistent_reply_keyboard(client):
    """`/menu` (and `/start` via the alias) attach the persistent reply
    keyboard. Buttons carry the label as their `text` — Telegram sends
    that text back to the bot when tapped (no callback_query)."""
    with patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/menu"))
    assert resp.status_code == 200
    markup = mock_send.call_args.kwargs.get("reply_markup")
    assert markup is not None
    assert markup.get("is_persistent") is True
    assert markup.get("resize_keyboard") is True
    # Two columns, derived from the source rather than hard-coded: a test that
    # breaks whenever a button is added is pinning the count, not the layout.
    expected_rows = -(-len(MAIN_MENU_ACTIONS) // 2)
    assert len(markup["keyboard"]) == expected_rows
    flattened = [b["text"] for row in markup["keyboard"] for b in row]
    assert flattened == [label for _, label in MAIN_MENU_ACTIONS]


def test_start_aliases_menu(client):
    with patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/start"))
    assert resp.status_code == 200
    markup = mock_send.call_args.kwargs.get("reply_markup")
    assert markup is not None
    assert markup.get("is_persistent") is True


# --- Reply-keyboard label routing ---


@pytest.mark.parametrize(
    "label,path,method",
    [
        ("🛒 Mercado", "/market", "GET"),
        ("📋 Alinear", "/lineups/auto-pick", "POST"),
        ("💡 Recomendar", "/budget/recommendations", "GET"),
        ("💸 Pujar", "/market/auto-bid", "POST"),
        ("🧹 Scraper", "/scraper/trigger", "POST"),
        ("📥 Ofertas", "/offers/inbox", "POST"),
        ("🚨 Emergencia", "/emergency/clausulazo/preview", "POST"),
    ],
)
def test_reply_keyboard_label_dispatches_action(client, label, path, method):
    """Tapping a button on the persistent keyboard sends the label as
    plain text; the bot must route it to the matching api endpoint."""
    with patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        resp = _post(client, _update(_VALID_CHAT, label))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(_API_URL, path, method=method, params=None)


def test_reply_keyboard_analizar_label_opens_picker(client):
    """The '📊 Analizar' label opens the manager picker (no direct api
    call), same as the `/analizar` slash command."""
    fake_managers = [
        {"id": 1, "name": "Jorge", "is_me": True},
        {"id": 2, "name": "Pepe", "is_me": False},
    ]
    with patch(
        "packages.biwenger_tools.bot.app.api_client.list_managers",
        return_value=fake_managers,
    ), patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "📊 Analizar"))
    assert resp.status_code == 200
    mock_call.assert_not_called()
    markup = mock_send.call_args.kwargs.get("reply_markup")
    assert markup is not None
    # Manager picker is still INLINE (one-shot two-step flow).
    assert "inline_keyboard" in markup


# --- callback_query handling (inline keyboards — manager picker only) ---


def test_analizar_id_callback_calls_teams_with_filter(client):
    """A manager tap calls `/teams?manager=<id>` and edits the picker."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_text"
    ) as mock_edit, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "analizar:7"))
    assert resp.status_code == 200
    mock_edit.assert_called_once()
    mock_call.assert_called_once_with(
        _API_URL, "/teams", method="GET", params={"manager": "7"}
    )


def test_analizar_all_callback_calls_teams_without_filter(client):
    """The TODOS tap fires `/teams` with no `manager` param (legacy flow)."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_text"
    ), patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "analizar:all"))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(_API_URL, "/teams", method="GET", params=None)


def test_emergencia_confirm_callback_calls_execute_with_query_params(client):
    """`e:c:<player>:<owner>:<amount>` → POST /emergency/clausulazo/execute
    with the same three ids the user saw and approved in the preview.
    The preview text stays intact (only its inline keyboard is stripped)
    and the "ejecutando…" status arrives as a fresh send."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ) as mock_strip, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "e:c:42:7:5000000"))
    assert resp.status_code == 200
    # Preview keyboard removed (no text edit so the preview stays readable).
    mock_strip.assert_called_once()
    assert mock_strip.call_args.kwargs["reply_markup"] == {"inline_keyboard": []}
    # New "ejecutando…" message goes as a fresh send.
    mock_send.assert_called_once()
    assert "ejecutando" in mock_send.call_args.kwargs["text"].lower()
    mock_call.assert_called_once_with(
        _API_URL,
        "/emergency/clausulazo/execute",
        method="POST",
        params={"player_id": "42", "owner_id": "7", "amount": "5000000"},
    )


def test_emergencia_selector_position_callback_refines_with_force_position(client):
    """`e:p:<position>` → POST /preview?force_position=<position>.
    Strips the selector keyboard so it can't be re-tapped."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ) as mock_strip, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ), patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "e:p:3"))
    assert resp.status_code == 200
    mock_strip.assert_called_once()
    mock_call.assert_called_once_with(
        _API_URL,
        "/emergency/clausulazo/preview",
        method="POST",
        params={"force_position": "3"},
    )


def test_emergencia_selector_weakest_callback_refines_with_force_weakest(client):
    """`e:m` → POST /preview?force_weakest=1."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ), patch("packages.biwenger_tools.bot.app.send_telegram_message"), patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "e:m"))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(
        _API_URL,
        "/emergency/clausulazo/preview",
        method="POST",
        params={"force_weakest": "1"},
    )


def test_emergencia_cancel_callback_edits_message_and_does_not_call_api(client):
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_text"
    ) as mock_edit, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "e:n"))
    assert resp.status_code == 200
    mock_call.assert_not_called()
    text = mock_edit.call_args.kwargs.get("text", "")
    assert "cancelada" in text.lower()


def test_emergencia_confirm_with_malformed_payload_is_ignored(client):
    """A malformed `e:c:not_a_number` callback must not POST to /execute
    (Biwenger would 400 with no useful context). Drop on the floor."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_text"
    ), patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "e:c:notanint:7:5000000"))
    assert resp.status_code == 200
    mock_call.assert_not_called()


def test_unknown_callback_prefix_is_ignored(client):
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "bogus:value"))
    assert resp.status_code == 200
    mock_call.assert_not_called()


# --- /ofertas callback (o:a|r|i:<id>) handling ----------------------------


def test_ofertas_accept_callback_posts_decide_accepted(client):
    """`o:a:<id>` → POST /offers/decide?decision=accepted; keyboard stripped.
    Also: the callback ack carries a "⏳ Aceptando…" toast so the user gets
    instant feedback while the cold-start api PUT runs in background."""
    with patch(
        "packages.biwenger_tools.bot.app.answer_callback_query"
    ) as mock_ack, patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ) as mock_strip, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "o:a:12345"))
    assert resp.status_code == 200
    mock_strip.assert_called_once()
    # answer_callback_query was called with the "⏳ Aceptando…" toast.
    ack_args = mock_ack.call_args
    assert ack_args.kwargs.get("text", "") or ack_args.args[-1:] == ()
    # The toast text is the third positional arg (token, cb_id, text=) — assert
    # via kwargs since the call uses keyword form.
    assert "Aceptando" in mock_ack.call_args.kwargs.get("text", "")
    mock_call.assert_called_once_with(
        _API_URL,
        "/offers/decide",
        method="POST",
        params={"offer_id": "12345", "decision": "accepted"},
    )


def test_ofertas_reject_callback_posts_decide_rejected(client):
    """`o:r:<id>` → POST /offers/decide?decision=rejected + "⏳ Rechazando…" toast."""
    with patch(
        "packages.biwenger_tools.bot.app.answer_callback_query"
    ) as mock_ack, patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ), patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "o:r:12345"))
    assert resp.status_code == 200
    assert "Rechazando" in mock_ack.call_args.kwargs.get("text", "")
    mock_call.assert_called_once_with(
        _API_URL,
        "/offers/decide",
        method="POST",
        params={"offer_id": "12345", "decision": "rejected"},
    )


def test_ofertas_ignore_callback_edits_message_and_does_not_call_api(client):
    """`o:i:<id>` strips the keyboard, writes "ignorada" across the offer,
    and never hits the api.

    The id used to be the whole message. It is no longer quoted because the
    offer it belongs to is right underneath — see `_verdict_over`."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ), patch("packages.biwenger_tools.bot.app.edit_message_text") as mock_edit, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "o:i:12345"))
    assert resp.status_code == 200
    mock_call.assert_not_called()
    text = mock_edit.call_args.kwargs.get("text", "")
    assert "ignorada" in text.lower()


def test_ofertas_malformed_callback_is_ignored(client):
    """Garbage in the `o:` payload must not hit the api."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "o:x:999"))
    assert resp.status_code == 200
    mock_call.assert_not_called()


def test_ofertas_non_int_offer_id_is_ignored(client):
    """`o:a:notanint` must NOT POST (would 400 server-side with no context)."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ), patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "o:a:notanint"))
    assert resp.status_code == 200
    mock_call.assert_not_called()


# --- /help, /version, unknown ---


def test_help_sends_message(client):
    with patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/help"))
    assert resp.status_code == 200
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs.get("chat_id") == _VALID_CHAT


def test_version_includes_bot_and_api(client):
    """`/version` includes the bot SHA and the api's /version response."""
    cfg.GIT_COMMIT = "abc1234"
    cfg.DEPLOY_TIME = "17/05/2026 14:00"
    api_meta = {
        "service": "biwenger-api",
        "commit": "def5678",
        "deploy_time": "18/05/2026 16:00",
    }
    with patch(
        "packages.biwenger_tools.bot.app.api_client.get_api_version",
        return_value=api_meta,
    ), patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/version"))
    assert resp.status_code == 200
    text = mock_send.call_args.kwargs.get("text", "")
    assert "abc1234" in text
    assert "17/05/2026 14:00" in text
    assert "def5678" in text
    assert "18/05/2026 16:00" in text


def test_version_tolerates_api_unreachable(client):
    """If biwenger-api /version fails, bot still reports its own version."""
    cfg.GIT_COMMIT = "abc1234"
    cfg.DEPLOY_TIME = "17/05/2026 14:00"
    with patch(
        "packages.biwenger_tools.bot.app.api_client.get_api_version",
        return_value=None,
    ), patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/version"))
    assert resp.status_code == 200
    text = mock_send.call_args.kwargs.get("text", "")
    assert "abc1234" in text
    assert "unreachable" in text


def test_unknown_command_is_ignored(client):
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _update(_VALID_CHAT, "/unknown"))
    assert resp.status_code == 200
    mock_call.assert_not_called()
    mock_send.assert_not_called()


def test_empty_body_does_not_crash(client):
    resp = client.post(
        "/telegram/webhook",
        data="",
        content_type="application/json",
        headers={"X-Telegram-Bot-Api-Secret-Token": _VALID_SECRET},
    )
    assert resp.status_code == 200


# --- Draft group: routing and command surface -----------------------------


@pytest.mark.parametrize(
    "command,path,method,params",
    [
        (
            "/soy Jorge",
            "/draft/register",
            "POST",
            {"telegram_user_id": "777", "name": "Jorge"},
        ),
        ("/estado", "/draft/state", "GET", None),
        (
            "/deshacer",
            "/draft/undo",
            "POST",
            {"telegram_user_id": "777"},
        ),
        ("/exportar", "/draft/export", "GET", None),
    ],
)
def test_draft_command_from_group_reaches_right_api_path(
    client, command, path, method, params
):
    with patch(
        "packages.biwenger_tools.bot.app._call_draft_api",
        return_value={"message": "ok"},
    ) as mock_call, patch("packages.biwenger_tools.bot.app.send_telegram_message"):
        resp = _post(client, _group_update(_VALID_DRAFT_CHAT, command, "777"))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(path, method, params)


def test_pick_command_calls_draft_pick_with_query(client):
    with patch(
        "packages.biwenger_tools.bot.app._call_draft_api",
        return_value={"status": "ok", "message": "Fichado: Rodrygo"},
    ) as mock_call, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _group_update(_VALID_DRAFT_CHAT, "/pick Rodrygo", "777"))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(
        "/draft/pick", "POST", {"telegram_user_id": "777", "query": "Rodrygo"}
    )
    assert "Fichado: Rodrygo" in mock_send.call_args.kwargs.get("text", "")


def test_pick_ambiguous_renders_candidate_keyboard(client):
    """An ambiguous /pick renders one button per candidate, callback_data
    `d:<requesting_user_id>:<player_id>` — so a later tap both resolves the
    player and can verify the tapper is the same user who ran /pick."""
    candidates = [
        {"player_id": 1, "name": "Rodrygo", "team": "Real Madrid", "price": 20_000_000},
        {"player_id": 2, "name": "Rodri", "team": "Man City", "price": 15_000_000},
    ]
    with patch(
        "packages.biwenger_tools.bot.app._call_draft_api",
        return_value={
            "status": "ambiguous",
            "candidates": candidates,
            "message": "¿Cuál de estos?",
        },
    ), patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _group_update(_VALID_DRAFT_CHAT, "/pick rodri", "777"))
    assert resp.status_code == 200
    markup = mock_send.call_args.kwargs.get("reply_markup")
    assert markup is not None
    rows = markup["inline_keyboard"]
    assert len(rows) == 2
    assert rows[0][0]["callback_data"] == "d:777:1"
    assert rows[1][0]["callback_data"] == "d:777:2"


def test_bare_soy_posts_the_manager_picker_instead_of_failing(client):
    """`/soy` with no name is what Telegram sends when the command is tapped
    from the `/` menu, so it must offer the managers rather than error out."""
    managers = [
        {"manager_id": 11, "name": "Ruben", "claimed_by": ""},
        {"manager_id": 22, "name": "Javi", "claimed_by": "999"},
    ]
    with patch(
        "packages.biwenger_tools.bot.app._call_draft_api",
        return_value={"managers": managers, "message": "¿Quién eres?"},
    ) as mock_api, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _group_update(_VALID_DRAFT_CHAT, "/soy", "777"))
    assert resp.status_code == 200
    assert mock_api.call_args.args[0] == "/draft/managers"
    rows = mock_send.call_args.kwargs["reply_markup"]["inline_keyboard"]
    assert rows[0][0]["callback_data"] == "s:11"
    assert rows[0][1]["text"].startswith("✅")


def test_soy_picker_tap_registers_that_manager(client):
    with patch(
        "packages.biwenger_tools.bot.app._call_draft_api",
        return_value={"message": "ok"},
    ) as mock_api, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ), patch(
        "packages.biwenger_tools.bot.app.answer_callback_query"
    ):
        resp = _post(
            client, _callback_update(_VALID_DRAFT_CHAT, "s:22", from_user_id="777")
        )
    assert resp.status_code == 200
    path, _method, payload = mock_api.call_args.args[:3]
    assert path == "/draft/register"
    assert payload == {"telegram_user_id": "777", "manager_id": "22"}


def test_exportar_sends_one_message_per_manager_block(client):
    """`messages` carries pre-split blocks — a single 105-pick listing would
    blow past Telegram's 4096-char limit."""
    with patch(
        "packages.biwenger_tools.bot.app._call_draft_api",
        return_value={"message": "resumen", "messages": ["Ruben\n1. Messi", "Javi"]},
    ), patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _group_update(_VALID_DRAFT_CHAT, "/exportar", "777"))
    assert resp.status_code == 200
    sent = [c.kwargs["text"] for c in mock_send.call_args_list]
    assert sent == ["resumen", "Ruben\n1. Messi", "Javi"]


def test_bare_pick_asks_for_a_player_without_calling_the_api(client):
    with patch("packages.biwenger_tools.bot.app._call_draft_api") as mock_api, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _group_update(_VALID_DRAFT_CHAT, "/pick", "777"))
    assert resp.status_code == 200
    mock_api.assert_not_called()
    assert "/pick" in mock_send.call_args.kwargs["text"]


def test_admin_command_from_draft_group_is_refused(client):
    """None of the owner-only commands are reachable from the draft group."""
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call, patch(
        "packages.biwenger_tools.bot.app._call_draft_api"
    ) as mock_draft_call, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _group_update(_VALID_DRAFT_CHAT, "/emergencia", "777"))
    assert resp.status_code == 200
    mock_call.assert_not_called()
    mock_draft_call.assert_not_called()
    mock_send.assert_not_called()


def test_group_message_does_not_consult_label_dispatch(client):
    """Plain chatter in the group that happens to match an admin menu label
    must not fire the matching admin action — the group branch must skip
    `_try_dispatch_label` entirely."""
    with patch(
        "packages.biwenger_tools.bot.app._try_dispatch_label"
    ) as mock_label, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _group_update(_VALID_DRAFT_CHAT, "🚨 Emergencia", "777"))
    assert resp.status_code == 200
    mock_label.assert_not_called()
    mock_call.assert_not_called()


def test_draft_command_from_unknown_chat_is_dropped(client):
    with patch("packages.biwenger_tools.bot.app._call_draft_api") as mock_call:
        resp = _post(client, _group_update("000111222", "/estado", "777"))
    assert resp.status_code == 200
    mock_call.assert_not_called()


def test_service_message_with_empty_text_is_ignored(client):
    """Telegram service messages (e.g. someone added to the group) carry a
    chat id but no `text` at all — must be dropped silently."""
    with patch("packages.biwenger_tools.bot.app._call_draft_api") as mock_call, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _service_message_update(_VALID_DRAFT_CHAT))
    assert resp.status_code == 200
    mock_call.assert_not_called()
    mock_send.assert_not_called()


# --- Draft group: callback routing (d: prefix + confirm) -------------------


@pytest.mark.parametrize("data", ["e:n", "o:a:123", "analizar:1"])
def test_admin_callback_prefix_from_draft_group_is_refused(client, data):
    with patch(
        "packages.biwenger_tools.bot.app.answer_callback_query"
    ) as mock_ack, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call, patch(
        "packages.biwenger_tools.bot.app.edit_message_text"
    ) as mock_edit, patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ) as mock_strip:
        resp = _post(client, _callback_update(_VALID_DRAFT_CHAT, data))
    assert resp.status_code == 200
    mock_call.assert_not_called()
    mock_edit.assert_not_called()
    mock_strip.assert_not_called()
    mock_ack.assert_called_once()


def test_draft_pick_confirm_rejects_different_user(client):
    """Only the user who ran /pick may confirm the ambiguous candidate —
    a tap from anyone else must not call the api nor strip the keyboard."""
    with patch(
        "packages.biwenger_tools.bot.app.answer_callback_query"
    ) as mock_ack, patch(
        "packages.biwenger_tools.bot.app._call_draft_api"
    ) as mock_call, patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ) as mock_strip:
        resp = _post(
            client,
            _callback_update(_VALID_DRAFT_CHAT, "d:777:1234", from_user_id="888"),
        )
    assert resp.status_code == 200
    mock_call.assert_not_called()
    mock_strip.assert_not_called()
    toast = mock_ack.call_args.kwargs.get("text", "")
    assert "Solo quien pidió" in toast


def test_draft_pick_confirm_succeeds_for_requesting_user(client):
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ) as mock_strip, patch(
        "packages.biwenger_tools.bot.app.edit_message_text"
    ) as mock_edit, patch(
        "packages.biwenger_tools.bot.app._call_draft_api",
        return_value={"message": "Fichaje confirmado: Rodrygo"},
    ) as mock_call:
        resp = _post(
            client,
            _callback_update(_VALID_DRAFT_CHAT, "d:777:1234", from_user_id="777"),
        )
    assert resp.status_code == 200
    mock_strip.assert_called_once()
    mock_call.assert_called_once_with(
        "/draft/pick/confirm",
        "POST",
        {"telegram_user_id": "777", "player_id": 1234},
    )
    text = mock_edit.call_args.kwargs.get("text", "")
    assert "Rodrygo" in text


def test_draft_callback_from_unknown_chat_is_dropped(client):
    with patch("packages.biwenger_tools.bot.app._call_draft_api") as mock_call:
        resp = _post(
            client,
            _callback_update("000111222", "d:777:1234", from_user_id="777"),
        )
    assert resp.status_code == 200
    mock_call.assert_not_called()


def test_soy_picker_tap_strips_the_keyboard(client):
    """The api round-trip takes seconds; a picker that still looks tappable
    gets tapped again, which is three registrations for one person."""
    with patch(
        "packages.biwenger_tools.bot.app._call_draft_api",
        return_value={"message": "ok"},
    ), patch("packages.biwenger_tools.bot.app.send_telegram_message"), patch(
        "packages.biwenger_tools.bot.app.answer_callback_query"
    ) as mock_ack, patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ) as mock_edit:
        resp = _post(
            client, _callback_update(_VALID_DRAFT_CHAT, "s:22", from_user_id="777")
        )
    assert resp.status_code == 200
    assert mock_ack.call_args.kwargs.get("text"), "acknowledge with a visible toast"
    assert mock_edit.call_args.kwargs["reply_markup"] is None


def test_every_menu_action_has_a_slash_command(client):
    """Wiring an action into `_ACTION_ROUTES` and the menu is not enough — the
    typed command goes through an explicit `elif` chain, and `/comparar`
    shipped registered in Telegram, listed in the help and reachable by button,
    while typing it did nothing at all."""
    from packages.biwenger_tools.bot.app import _ACTION_ROUTES, _dispatch_action

    source = inspect.getsource(sys.modules["packages.biwenger_tools.bot.app"])
    dispatched = set(re.findall(r'_dispatch_action\(\s*"([a-z_]+)"', source))

    # `analizar` opens the manager picker instead of dispatching directly.
    missing = set(_ACTION_ROUTES) - dispatched - {"analizar"}
    assert not missing, f"acciones sin comando: {sorted(missing)}"
    assert _dispatch_action  # imported for the reader, not called here


def test_comparar_command_dispatches(client):
    with patch("packages.biwenger_tools.bot.app._dispatch_action") as mock:
        resp = _post(client, _update(_VALID_CHAT, "/comparar"))
    assert resp.status_code == 200
    mock.assert_called_once()
    assert mock.call_args[0][0] == "comparar"


# --- The decision is written onto the offer it settled --------------------

_OFFER_TEXT = (
    "📥 Oferta entrante\n\n"
    "Jugador: Neto (MED)\n"
    "Cantidad: 788.400 €\n"
    "Recomendación: ✅ ACEPTAR"
)


def test_accepting_writes_the_verdict_onto_the_offer_message(client):
    """The record has to say which offer it settled. "Oferta Aceptada · id
    1657307609" named neither the player nor the price, leaving the reader to
    correlate an id against the message above."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ), patch("packages.biwenger_tools.bot.app.edit_message_text") as mock_edit, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(
            client, _callback_update(_VALID_CHAT, "o:a:12345", text=_OFFER_TEXT)
        )
    assert resp.status_code == 200
    mock_call.assert_called_once()
    text = mock_edit.call_args.kwargs.get("text", "")
    assert "OFERTA ACEPTADA" in text
    assert "Neto (MED)" in text  # the offer is still readable underneath
    assert "788.400" in text


def test_rejecting_says_so_rather_than_reusing_the_accept_banner(client):
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ), patch("packages.biwenger_tools.bot.app.edit_message_text") as mock_edit, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ):
        _post(client, _callback_update(_VALID_CHAT, "o:r:12345", text=_OFFER_TEXT))
    text = mock_edit.call_args.kwargs.get("text", "")
    assert "OFERTA RECHAZADA" in text


def test_a_failed_decision_leaves_the_offer_unstamped(client):
    """The outcome is Biwenger's to confirm. Stamping "ACEPTADA" on a transfer
    the api refused would be a message that lies."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ), patch("packages.biwenger_tools.bot.app.edit_message_text") as mock_edit, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api",
        side_effect=RuntimeError("boom"),
    ), patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        _post(client, _callback_update(_VALID_CHAT, "o:a:12345", text=_OFFER_TEXT))

    banners = [
        c.kwargs.get("text", "")
        for c in mock_edit.call_args_list
        if "ACEPTADA" in c.kwargs.get("text", "")
    ]
    assert banners == []
    mock_send.assert_called_once()  # the error still reaches the chat


def test_the_echoed_offer_text_is_escaped_before_it_goes_back_out():
    """Telegram's HTML parser is strict and this repo has been bitten twice.
    The body comes back as plain text and is re-sent inside an HTML message,
    so a `&` in a player's name must not be able to drop the whole thing."""
    from packages.biwenger_tools.bot.app import _verdict_over

    out = _verdict_over("Jugador: Sanders & Co <b>", "✅ <b>OK</b>")
    assert "&amp;" in out and "&lt;b&gt;" in out
    assert "<b>OK</b>" in out  # the banner keeps its own markup


def test_a_verdict_without_the_original_text_is_still_sent():
    """Telegram omits `text` for a media message, and an older offer message
    may predate this. Degrade to the banner alone rather than an empty edit."""
    from packages.biwenger_tools.bot.app import _verdict_over

    assert _verdict_over("", "⏰ <b>IGNORADA</b>") == "⏰ <b>IGNORADA</b>"


# --- Portadas (image attachments) ---


def _photo_update(chat_id, caption="Titular", file_ids=("small", "big")):
    return {
        "update_id": 1,
        "message": {
            "chat": {"id": chat_id},
            "from": {"id": 1},
            "caption": caption,
            "photo": [{"file_id": f} for f in file_ids],
        },
    }


def _document_update(chat_id, caption="Titular", mime_type="image/jpeg"):
    return {
        "update_id": 1,
        "message": {
            "chat": {"id": chat_id},
            "from": {"id": 1},
            "caption": caption,
            "document": {"file_id": "doc-1", "mime_type": mime_type},
        },
    }


def test_owner_document_publishes_the_portada(client):
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api_json",
        return_value={"message": "📰 Portada publicada"},
    ) as mock_call, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _document_update(_VALID_CHAT, "2026-08-14 Titular"))

    assert resp.status_code == 200
    mock_call.assert_called_once_with(
        _API_URL,
        "/periodico/portada",
        payload={
            "file_id": "doc-1",
            "caption": "2026-08-14 Titular",
            "kind": "document",
        },
        timeout=180,
    )
    # Ack first, then whatever the api wrote — verbatim.
    assert mock_send.call_count == 2
    assert "📰 Portada publicada" in mock_send.call_args.kwargs["text"]


def test_owner_photo_sends_the_largest_size(client):
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api_json",
        return_value={"message": "ok"},
    ) as mock_call, patch("packages.biwenger_tools.bot.app.send_telegram_message"):
        resp = _post(client, _photo_update(_VALID_CHAT))

    assert resp.status_code == 200
    assert mock_call.call_args.kwargs["payload"]["file_id"] == "big"
    assert mock_call.call_args.kwargs["payload"]["kind"] == "photo"


def test_draft_group_photo_is_ignored(client):
    """The league supergroup must not be able to publish front pages — every
    member can post a photo there."""
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api_json"
    ) as mock_call, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ) as mock_send:
        resp = _post(client, _photo_update(_VALID_DRAFT_CHAT))

    assert resp.status_code == 200
    mock_call.assert_not_called()
    mock_send.assert_not_called()


def test_portada_failure_is_reported_instead_of_leaving_the_ack_hanging(client):
    """The upload runs in a background thread; without this the owner watches
    "subiendo…" forever when the bucket refuses the write."""
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api_json",
        side_effect=RuntimeError("403 Forbidden"),
    ), patch("packages.biwenger_tools.bot.app.send_telegram_message") as mock_send:
        resp = _post(client, _document_update(_VALID_CHAT))

    assert resp.status_code == 200
    assert "❌" in mock_send.call_args.kwargs["text"]
    assert "403 Forbidden" in mock_send.call_args.kwargs["text"]


def test_non_image_document_falls_through_to_the_text_path(client):
    """A CSV dropped in the owner chat is not a front page."""
    with patch(
        "packages.biwenger_tools.bot.app.api_client.call_api_json"
    ) as mock_call, patch("packages.biwenger_tools.bot.app.send_telegram_message"):
        resp = _post(client, _document_update(_VALID_CHAT, mime_type="text/csv"))

    assert resp.status_code == 200
    mock_call.assert_not_called()
