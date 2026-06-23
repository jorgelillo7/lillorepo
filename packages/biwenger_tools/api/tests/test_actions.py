"""Unit tests for `api/logic/actions` — specifically the resilience of
multi-photo flows. Route wiring is tested in `test_routes.py`."""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch


def _patches(target):
    return f"packages.biwenger_tools.api.logic.actions.{target}"


def test_run_teams_all_mode_continues_after_first_photo_fails():
    """A single Telegram refusal in the middle of an /analizar TODOS run
    must not skip the remaining manager squads or the mercado photo. The
    failure is reported per-image (via the fallback) and the sent count
    reflects only the photos that actually landed."""
    biwenger = MagicMock()
    biwenger.user_id = 1
    biwenger.get_league_users.return_value = {1: "Me", 2: "Rival"}
    biwenger.get_manager_squad.return_value = []
    biwenger.get_market_players.return_value = []

    from packages.biwenger_tools.api.logic.orchestration import OrchestratorContext

    ctx = OrchestratorContext(
        biwenger=biwenger,
        biwenger_players={},
        jp_index={"by_name": {}, "by_slug": {}},
    )

    stack = ExitStack()
    stack.enter_context(patch(_patches("config")))
    stack.enter_context(patch(_patches("build_context"), return_value=ctx))
    stack.enter_context(
        patch(_patches("require_telegram"), return_value=("tok", "chat"))
    )
    stack.enter_context(patch(_patches("build_table_image"), return_value=b""))
    # First photo (Mi equipo) fails, the rest land. The mercado photo at the
    # end MUST still go out — that's the regression.
    mock_send = stack.enter_context(
        patch(
            _patches("send_image_or_text_fallback"),
            side_effect=[False, True, True],
        )
    )
    try:
        from packages.biwenger_tools.api.logic import actions

        result = actions.run_teams(manager_id=None)
    finally:
        stack.close()

    assert mock_send.call_count == 3  # me + 1 rival + mercado
    assert result["sent"] == 2  # only the two successes counted
    assert result["teams"] == 2
