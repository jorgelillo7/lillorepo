"""Tests for the post-deploy command registration: three blocks, each shown
only in its own chats."""

from unittest.mock import patch

import pytest

import packages.biwenger_tools.bot.config as cfg
from packages.biwenger_tools.bot import setup_commands

_SETUP = "packages.biwenger_tools.bot.setup_commands"


@pytest.fixture(autouse=True)
def chats(monkeypatch):
    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setattr(cfg, "TELEGRAM_CHAT_ID", "111")
    monkeypatch.setattr(cfg, "TELEGRAM_DRAFT_CHAT_ID", "-100222")
    monkeypatch.delenv("BIWENGER_BOT_URL", raising=False)


def _registered():
    with patch(f"{_SETUP}.configure_bot_commands") as configure:
        setup_commands.main()
    return [
        (call.args[1], call.kwargs.get("scope")) for call in configure.call_args_list
    ]


def test_setup_scopes_each_block_to_its_chats():
    calls = _registered()
    assert calls == [
        ([], None),
        (setup_commands.PUBLIC_COMMANDS, {"type": "all_private_chats"}),
        (setup_commands.COMMANDS, {"type": "chat", "chat_id": "111"}),
        (setup_commands.DRAFT_COMMANDS, {"type": "chat", "chat_id": "-100222"}),
    ]


def test_setup_refuses_to_publish_without_the_owner_chat(monkeypatch):
    monkeypatch.setattr(cfg, "TELEGRAM_CHAT_ID", "")
    with patch(f"{_SETUP}.configure_bot_commands") as configure:
        with pytest.raises(SystemExit):
            setup_commands.main()
    configure.assert_not_called()


def test_the_owner_block_holds_no_draft_command():
    owner = {c["command"] for c in setup_commands.COMMANDS}
    draft = {c["command"] for c in setup_commands.DRAFT_COMMANDS}
    assert owner.isdisjoint(draft)
    assert "publico" in owner
