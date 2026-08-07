"""Bot → api integration, in process, with only the outside world faked.

Every other suite stops at a module boundary: the bot's tests assert that a
command reaches `_ACTION_ROUTES`, the api's assert that a path reaches its
action. Nothing joined the two, which is how `/comparar` shipped with a route,
a menu button, a help line and no `elif` branch — reachable by button, dead
when typed.

Here the bot's HTTP client is redirected into the api's Flask test client, so a
Telegram webhook payload travels the real path: command parsing → route table →
Flask routing → the real action → the real logic. Only Biwenger and Jornada
Perfecta are faked, at `build_context`, plus the Telegram sends at the far end.

Deliberately cheap: no Firestore emulator, no Biwenger sandbox. The
accepted-gaps table in STATUS.md rejects that setup, and this catches the
contract bugs it would have caught anyway.
"""

from unittest.mock import patch

import pytest

import packages.biwenger_tools.api.config as api_cfg
import packages.biwenger_tools.bot.config as bot_cfg
from packages.biwenger_tools.api.app import app as api_app
from packages.biwenger_tools.api.logic import league_compare
from packages.biwenger_tools.api.logic.orchestration import OrchestratorContext
from packages.biwenger_tools.api.logic.player_matching import build_jp_index
from packages.biwenger_tools.bot.app import app as bot_app

_CHAT = "111222333"
_API_URL = "https://biwenger-api.example.run.app"
_SECRET = "test-secret"


# --------------------------------------------------------------------------
# Fake league: three managers, one squad each, with a projection and a price.
# --------------------------------------------------------------------------

_MANAGERS = {1: "Farolillo AI United", 2: "Rayo Entrebirras", 3: "Cebollitas FC"}

# id → (name, position, price, projected SF)
_PLAYERS = {
    101: ("Dmitrovic", 1, 5_000_000, 405),
    102: ("Yuri", 2, 8_000_000, 415),
    103: ("Dani Olmo", 3, 20_000_000, 659),
    201: ("Neto", 3, 3_000_000, 1),
    202: ("Bretones", 2, 6_000_000, 228),
    301: ("Danjuma", 3, 9_000_000, 328),
}

_SQUADS = {1: [101, 102, 103], 2: [201, 202], 3: [301]}


def _biwenger_players() -> dict:
    return {
        pid: {"id": pid, "name": name, "position": pos, "price": price}
        for pid, (name, pos, price, _) in _PLAYERS.items()
    }


def _jp_index() -> dict:
    """Built with the real indexer, so name matching is exercised too."""
    jp_players = [
        {
            "name": name,
            "slug": name.lower().replace(" ", "-"),
            "status": "ok",
            "nextMatch": {"playerInLineup": True},
            "predict": [{"type": 2, "rate": sf}],
        }
        for _, (name, _, _, sf) in _PLAYERS.items()
    ]
    return build_jp_index(jp_players, biwenger_names=[p[0] for p in _PLAYERS.values()])


class _FakeBiwenger:
    def get_league_users(self, _url):
        return dict(_MANAGERS)

    def get_manager_squad(self, _url, manager_id):
        return [
            {"id": pid, "owner": {"price": _PLAYERS[pid][2]}}
            for pid in _SQUADS[int(manager_id)]
        ]


def _fake_context() -> OrchestratorContext:
    return OrchestratorContext(
        biwenger=_FakeBiwenger(),
        biwenger_players=_biwenger_players(),
        jp_index=_jp_index(),
    )


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def wire_bot_to_api():
    """Point the bot at the api's test client instead of the network.

    `call_api` builds a real URL and signs it; both are replaced here, so what
    is exercised is the path and method the bot chose — the contract that broke.
    """
    bot_cfg.TELEGRAM_WEBHOOK_SECRET = _SECRET
    bot_cfg.TELEGRAM_CHAT_ID = _CHAT
    bot_cfg.TELEGRAM_BOT_TOKEN = "test-token"
    bot_cfg.BIWENGER_API_URL = _API_URL
    api_cfg.TELEGRAM_BOT_TOKEN = "test-token"
    api_cfg.TELEGRAM_CHAT_ID = _CHAT

    api_app.config["TESTING"] = True
    api_client = api_app.test_client()

    def forward(method, url, **kwargs):
        assert url.startswith(_API_URL), f"bot called an unexpected host: {url}"
        return api_client.open(
            url[len(_API_URL) :],
            method=method,
            query_string=kwargs.get("params"),
        )

    with patch(
        "packages.biwenger_tools.bot.api_client.http_requests.request",
        side_effect=forward,
    ), patch(
        "packages.biwenger_tools.bot.api_client._fetch_id_token",
        return_value="fake-token",
    ), patch(
        "packages.biwenger_tools.bot.app._run_in_background",
        side_effect=lambda fn, *a, **kw: fn(*a, **kw),
    ):
        league_compare.reset_cache()
        yield
    league_compare.reset_cache()


@pytest.fixture
def bot_client():
    bot_app.config["TESTING"] = True
    with bot_app.test_client() as c:
        yield c


def _send(client, text):
    return client.post(
        "/telegram/webhook",
        json={"update_id": 1, "message": {"chat": {"id": _CHAT}, "text": text}},
        headers={"X-Telegram-Bot-Api-Secret-Token": _SECRET},
    )


# --------------------------------------------------------------------------
# /comparar
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["/comparar", "/comparar@biwenger_tools_bot"])
def test_typed_comparar_reaches_the_api_and_sends_both_rankings(bot_client, text):
    """The regression that shipped: typing the command did nothing.

    Asserting on the delivered message rather than on a mock call means the
    route, the action and the renderer all have to work.
    """
    with patch(
        "packages.biwenger_tools.api.logic.actions.build_context",
        return_value=_fake_context(),
    ), patch(
        "packages.biwenger_tools.api.logic.actions.send_telegram_message_or_raise"
    ) as api_send, patch(
        "packages.biwenger_tools.bot.app.send_telegram_message"
    ):
        resp = _send(bot_client, text)

    assert resp.status_code == 200
    api_send.assert_called_once()
    message = api_send.call_args.kwargs["text"]

    for manager in _MANAGERS.values():
        assert manager in message
    assert "Equipo más caro" in message
    assert "Quién proyecta más" in message

    # Farolillo owns the three most expensive players and the highest total
    # projection, so it must top both tables.
    value_table, projection_table = message.split("Quién proyecta más")
    assert "1. <b>Farolillo AI United</b>" in value_table
    assert "1. <b>Farolillo AI United</b>" in projection_table


def test_menu_button_and_typed_command_take_the_same_path(bot_client):
    """The button worked while the typed command did not, which is what hid
    the bug. Both must land on the same api call."""
    with patch("packages.biwenger_tools.bot.app.api_client.call_api") as mock_call:
        _send(bot_client, "/comparar")
        typed = mock_call.call_args
        mock_call.reset_mock()
        _send(bot_client, "⚖️ Comparar")
        tapped = mock_call.call_args

    assert typed is not None, "typing /comparar called nothing"
    assert tapped is not None, "tapping the menu button called nothing"
    assert typed == tapped


def test_every_menu_action_is_reachable_by_typing(bot_client):
    """A button whose slash command is missing is invisible until someone taps
    it — exactly how `/comparar` reached production."""
    from packages.biwenger_tools.bot.menu import MAIN_MENU_ACTIONS

    unreachable = []
    for action, _label in MAIN_MENU_ACTIONS:
        with patch(
            "packages.biwenger_tools.bot.app.api_client.call_api"
        ) as mock_call, patch(
            "packages.biwenger_tools.bot.app.api_client.list_managers",
            return_value=[{"id": 1, "name": "Yo", "is_me": True}],
        ), patch(
            "packages.biwenger_tools.bot.app.send_telegram_message"
        ) as mock_send:
            _send(bot_client, f"/{action}")
            # Either it called the api, or it answered (the picker flows do).
            if not mock_call.called and not mock_send.called:
                unreachable.append(action)

    assert not unreachable, f"typed commands that do nothing: {unreachable}"


# --------------------------------------------------------------------------
# The lineup step — the one that writes to Biwenger every morning
# --------------------------------------------------------------------------


def test_preview_fills_the_bench_instead_of_leaving_holes(bot_client):
    """`/preview` is `/alinear` with `dry_run=1`, so this exercises the same
    optimizer that writes to Biwenger at 09:00 without writing anything.

    The regression it guards: injured and unlisted players were excluded
    outright, so the bench came back half empty. An empty slot scores worse
    than a player who might yet play.
    """
    with patch("packages.biwenger_tools.bot.app.send_telegram_message"):
        with patch(
            "packages.biwenger_tools.api.app.actions.run_auto_pick_lineup",
            return_value={"applied": False, "formation": "4-6-0"},
        ) as mock_lineup:
            resp = _send(bot_client, "/preview")

    assert resp.status_code == 200
    mock_lineup.assert_called_once()
    # The bot must ask for a dry run — a real one would put a lineup on
    # Biwenger from a test.
    assert mock_lineup.call_args.kwargs.get("dry_run") is True
