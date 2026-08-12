"""Unit tests for `api/logic/actions` — specifically the resilience of
multi-photo flows. Route wiring is tested in `test_routes.py`."""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from packages.biwenger_tools.api.logic import league_compare


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


def test_run_teams_all_mode_survives_a_broken_market():
    """The squads are already in the chat when the market is read.

    A closed market used to raise inside `get_market_players`, so the route
    answered 500 *after* every squad photo had been delivered — the user saw
    all the images arrive and then a bare error. The squads must still count
    and the run must succeed.
    """
    biwenger = MagicMock()
    biwenger.user_id = 1
    biwenger.get_league_users.return_value = {1: "Me", 2: "Rival"}
    biwenger.get_manager_squad.return_value = []
    biwenger.get_market_players.side_effect = AttributeError(
        "'NoneType' object has no attribute 'get'"
    )

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
    stack.enter_context(
        patch(_patches("send_image_or_text_fallback"), return_value=True)
    )
    notice = stack.enter_context(patch(_patches("send_telegram_message")))
    try:
        from packages.biwenger_tools.api.logic import actions

        result = actions.run_teams(manager_id=None)
    finally:
        stack.close()

    assert result["sent"] == 2  # me + rival landed
    assert result["market"] == 0
    notice.assert_called_once()
    assert "Mercado" in notice.call_args.kwargs["text"]


# --- league comparison ---


def _squad(value, projection):
    return {"value": value, "projection": projection, "size": 15}


def test_render_says_who_bought_best_only_when_there_is_a_cost():
    """Right after the draft "what it cost against what it is worth" is the
    interesting number. A month later half a squad arrived by clause and nobody
    remembers what it cost, so the same renderer must ask a different question."""
    with_cost = {"A": {**_squad(60_000_000, 5000), "gain": 9_000_000}}
    without = {"A": _squad(60_000_000, 5000)}

    assert "Quién compró mejor" in league_compare.render(with_cost, "t")
    assert "sobre lo que pagó" in league_compare.render(with_cost, "t")
    assert "Equipo más caro" in league_compare.render(without, "t")
    assert "sobre lo que pagó" not in league_compare.render(without, "t")


def test_the_two_rankings_are_independent():
    """Value and projection answer different questions; the most expensive
    squad is not automatically the one that scores."""
    summary = {
        "Caro": _squad(60_000_000, 3000),
        "Barato": _squad(40_000_000, 5000),
    }

    assert league_compare.rank(summary, "value") == ["Caro", "Barato"]
    assert league_compare.rank(summary, "projection") == ["Barato", "Caro"]


def test_the_comparison_is_cached_so_a_second_tap_costs_nothing():
    """Nine Biwenger reads hang off a button, against a budget the whole league
    shares."""
    league_compare.reset_cache()
    ctx = object()
    with patch.object(
        league_compare, "collect", return_value={"A": _squad(1, 1)}
    ) as collect:
        league_compare.collect_cached(ctx)
        league_compare.collect_cached(ctx)

    collect.assert_called_once()
    league_compare.reset_cache()


def test_render_values_ranks_every_squad_and_totals_the_league():
    """The daily snapshot: value only. Projection is deliberately absent —
    it changes every matchday and the lineup message sent moments earlier
    already covers it, while value is the slow number worth photographing."""
    summary = {
        "Jorge": {"value": 57_700_000, "projection": 4_326},
        "Ruben": {"value": 61_200_000, "projection": 4_100},
        "Javi": {"value": 49_050_000, "projection": 3_900},
    }
    msg = league_compare.render_values(summary)

    assert msg.index("Ruben") < msg.index("Jorge") < msg.index("Javi")
    assert "57,70M" in msg
    assert "Total de la liga: 167,95M" in msg
    assert "SF" not in msg


def test_collect_survives_a_player_jornada_perfecta_does_not_carry():
    """A squad can hold a player with no JP match — a fresh signing JP has
    not listed yet. That squad must still be measured: its value is known
    from Biwenger alone, and the missing projection counts as zero rather
    than taking the whole league ranking down."""
    from unittest.mock import MagicMock, patch

    biwenger = MagicMock()
    biwenger.get_league_users.return_value = {1: "Jorge"}
    biwenger.get_manager_squad.return_value = [{"id": 10}, {"id": 11}]
    ctx = MagicMock(biwenger=biwenger, biwenger_players={}, jp_index={})

    rows = [
        {"price": 7_400_000, "jp_player": {"predict": [{"type": 2, "rate": 538}]}},
        {"price": 2_200_000, "jp_player": None},  # signed, not in JP yet
    ]
    league_compare.reset_cache()
    with patch(
        "packages.biwenger_tools.api.logic.league_compare.build_squad_rows",
        return_value=rows,
    ):
        summary = league_compare.collect(ctx)

    assert summary["Jorge"]["value"] == 9_600_000
    assert summary["Jorge"]["projection"] == 538
    league_compare.reset_cache()
