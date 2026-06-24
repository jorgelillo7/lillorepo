"""Tests for the Biwenger bot webhook."""

from unittest.mock import patch

import pytest

import packages.biwenger_tools.bot.config as cfg
from packages.biwenger_tools.bot.app import app

_VALID_SECRET = "test-secret"
_VALID_CHAT = "111222333"
_API_URL = "https://biwenger-api.example.run.app"


@pytest.fixture(autouse=True)
def patch_config():
    """Set known config values for every test."""
    cfg.TELEGRAM_WEBHOOK_SECRET = _VALID_SECRET
    cfg.TELEGRAM_CHAT_ID = _VALID_CHAT
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


def _callback_update(chat_id, data, message_id=42, query_id="cb-1"):
    """Webhook body for an inline-keyboard tap."""
    return {
        "update_id": 2,
        "callback_query": {
            "id": query_id,
            "data": data,
            "message": {"chat": {"id": chat_id}, "message_id": message_id},
        },
    }


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
    # 8 actions arranged in 2 columns → 4 rows
    assert len(markup["keyboard"]) == 4
    flattened = [b["text"] for row in markup["keyboard"] for b in row]
    assert "📊 Analizar" in flattened
    assert "💸 Pujar" in flattened
    assert "🧹 Scraper" in flattened
    assert "📥 Ofertas" in flattened
    assert "🚨 Emergencia" in flattened


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
    """`o:a:<id>` → POST /offers/decide?decision=accepted; keyboard stripped."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ) as mock_strip, patch(
        "packages.biwenger_tools.bot.app.api_client.call_api"
    ) as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "o:a:12345"))
    assert resp.status_code == 200
    mock_strip.assert_called_once()
    mock_call.assert_called_once_with(
        _API_URL,
        "/offers/decide",
        method="POST",
        params={"offer_id": "12345", "decision": "accepted"},
    )


def test_ofertas_reject_callback_posts_decide_rejected(client):
    """`o:r:<id>` → POST /offers/decide?decision=rejected."""
    with patch("packages.biwenger_tools.bot.app.answer_callback_query"), patch(
        "packages.biwenger_tools.bot.app.edit_message_reply_markup"
    ), patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        resp = _post(client, _callback_update(_VALID_CHAT, "o:r:12345"))
    assert resp.status_code == 200
    mock_call.assert_called_once_with(
        _API_URL,
        "/offers/decide",
        method="POST",
        params={"offer_id": "12345", "decision": "rejected"},
    )


def test_ofertas_ignore_callback_edits_message_and_does_not_call_api(client):
    """`o:i:<id>` strips the keyboard, edits the message text to "ignorada",
    and never hits the api."""
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
    assert "12345" in text


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
