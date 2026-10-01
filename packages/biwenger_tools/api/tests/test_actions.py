"""Unit tests for `api/logic/actions` — specifically the resilience of
multi-photo flows. Route wiring is tested in `test_routes.py`."""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from packages.biwenger_tools.api import config
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


def test_collect_ranks_every_squad_on_the_same_oraculo_scale():
    """`/comparar`'s whole point is a cross-manager ranking, so every squad
    read inside one `collect()` call must be built with the same Oráculo
    index and scale — mixing a blended squad with a raw one is not a
    ranking on one scale, it is noise.

    Ana's player projects lower on raw JP (300) than Beto's (350). Oráculo
    rates Ana's player highly and Beto's poorly; blended through the shared
    scale, Ana's projection overtakes Beto's. That inversion can only appear
    if `collect` reads the blend (not the raw JP rate) for both squads.
    """
    from unittest.mock import MagicMock

    from packages.biwenger_tools.api.logic import custom_prediction as cp
    from packages.biwenger_tools.api.logic import rows as rows_mod
    from packages.biwenger_tools.api.logic.player_matching import build_jp_index

    def _jp(name, rate):
        return {
            "name": name,
            "slug": name.lower(),
            "predict": [{"type": 2, "rate": rate}],
        }

    def _oraculo(name, points):
        return {
            "playerName": name,
            "slug": name.lower(),
            "predictedPoints": points,
            "chance": 90,
        }

    biwenger_players = {
        1: {"id": 1, "name": "Alpha", "position": 3, "price": 1_000_000},
        2: {"id": 2, "name": "Beta", "position": 3, "price": 1_000_000},
    }
    jp_index = build_jp_index([_jp("Alpha", 300), _jp("Beta", 350)])
    oraculo_index = rows_mod.build_oraculo_index(
        [_oraculo("Alpha", 5.0), _oraculo("Beta", 1.0)]
    )
    scale = cp.ProjectionScale(
        oraculo=(1.0, 2.0, 3.0, 4.0, 5.0), jp=(100.0, 200.0, 300.0, 400.0, 500.0)
    )

    biwenger = MagicMock()
    biwenger.get_league_users.return_value = {1: "Ana", 2: "Beto"}
    biwenger.get_manager_squad.side_effect = lambda url, manager_id: (
        [{"id": 1}] if manager_id == 1 else [{"id": 2}]
    )

    ctx = MagicMock(
        biwenger=biwenger,
        biwenger_players=biwenger_players,
        jp_index=jp_index,
        oraculo_index=oraculo_index,
        oraculo_scale=scale,
    )

    league_compare.reset_cache()
    summary = league_compare.collect(ctx)
    league_compare.reset_cache()

    # Both totals must reflect the blend — pinning only Ana's would also
    # pass if Beto's squad had silently stayed on the raw JP rate.
    assert summary["Ana"]["projection"] == 360  # 300 blended up via Oráculo
    assert summary["Beto"]["projection"] == 275  # 350 blended down via Oráculo
    assert league_compare.rank(summary, "projection") == ["Ana", "Beto"]


# --- the protection watch (daily digest) -----------------------------------

_SEASON_START = [{"type": "seasonStarted", "content": {}, "date": 1}]


def _watch_ctx(my_lock):
    """Me (1) with one player whose clause lock is `my_lock`; one rival (2)
    at the 50M start with an empty squad."""
    biwenger = MagicMock()
    biwenger.user_id = 1
    biwenger.get_league_users.return_value = {1: "Me", 2: "Luceneta"}
    biwenger.get_all_board_messages.return_value = _SEASON_START

    def squad(_url, manager_id):
        if manager_id != 1:
            return []
        return [{"id": 7, "owner": {"clause": 9_000_000, "clauseLockedUntil": my_lock}}]

    biwenger.get_manager_squad.side_effect = squad
    from packages.biwenger_tools.api.logic.orchestration import OrchestratorContext

    return OrchestratorContext(
        biwenger=biwenger,
        biwenger_players={7: {"id": 7, "name": "Parrott", "position": 2, "price": 1}},
        jp_index={"by_name": {}, "by_slug": {}},
    )


def _watch(ctx):
    from packages.biwenger_tools.api.logic import actions

    with (
        patch(_patches("require_telegram"), return_value=("tok", "chat")),
        patch(_patches("send_telegram_message_or_raise")) as mock_send,
        patch(_patches("pact_store.load"), return_value=set()),
        patch(_patches("board_archive_store.load"), return_value=[]),
    ):
        result = actions.run_protection_watch(ctx)
    return result, mock_send


def test_protection_watch_reads_nothing_more_on_a_quiet_morning():
    """No lock ending means no board read and no rival squads: a normal
    morning costs the digest one squad read and no message."""
    ctx = _watch_ctx(my_lock=None)
    result, mock_send = _watch(ctx)
    mock_send.assert_not_called()
    ctx.biwenger.get_all_board_messages.assert_not_called()
    assert result == {"ending": 0, "sent": 0}


def test_protection_watch_warns_when_a_lock_ends_and_a_rival_can_pay():
    import time

    ctx = _watch_ctx(my_lock=int(time.time()) + 3_600)
    result, mock_send = _watch(ctx)
    text = mock_send.call_args.kwargs["text"]
    assert "Parrott" in text and "Luceneta" in text
    assert result == {"ending": 1, "sent": 1}


# --- /saldos reads the board archive too -----------------------------------


def _money(ctx, archive):
    from packages.biwenger_tools.api.logic import actions

    with patch(_patches("board_archive_store.load"), **archive) as load:
        result = actions._league_money(ctx.biwenger, ctx.biwenger_players)
    return result, load


def test_league_money_adds_what_only_the_archive_holds():
    ctx = _watch_ctx(my_lock=None)
    sale = {
        "type": "transfer",
        "content": [{"from": {"id": 2}, "amount": 5_000_000}],
        "date": 2,
    }
    (rows, _, _, _, lost), load = _money(ctx, {"return_value": [sale, *_SEASON_START]})
    load.assert_called_once_with(config.CURRENT_SEASON)
    assert lost == 1
    rival = next(r for r in rows if r["id"] == 2)
    assert rival["cash"] == 55_000_000


def test_an_unreadable_archive_leaves_the_live_board_and_says_so():
    ctx = _watch_ctx(my_lock=None)
    (rows, _, _, _, lost), _ = _money(ctx, {"side_effect": RuntimeError("503")})
    assert lost is None
    assert next(r for r in rows if r["id"] == 2)["cash"] == 50_000_000


# --- the fixture run behind the market's "Calendario" column ---------------


def _round_payload(round_id, games, rounds=None):
    return {"id": round_id, "games": games, "season": {"rounds": rounds or []}}


def test_read_fixture_runs_walks_the_open_rounds():
    import time

    from packages.biwenger_tools.api.logic import actions

    soon = int(time.time()) + 86_400
    game = {
        "date": soon,
        "status": "pending",
        "home": {"id": 3, "difficulty": {"rating": 25}},
        "away": {"id": 8, "difficulty": {"rating": 94}},
    }
    current = _round_payload(
        4905,
        [],
        rounds=[{"id": 4905, "status": "finished"}, {"id": 4906, "status": "pending"}],
    )
    biwenger = MagicMock()
    biwenger.get_round.side_effect = lambda round_id=None: (
        current if round_id is None else _round_payload(round_id, [game])
    )
    upcoming = actions.read_fixture_runs(biwenger)
    assert upcoming == {3: [25], 8: [94]}


def test_read_fixture_runs_is_none_when_the_calendar_cannot_be_read():
    from packages.biwenger_tools.api.logic import actions

    biwenger = MagicMock()
    biwenger.get_round.side_effect = RuntimeError("cloudflare")
    assert actions.read_fixture_runs(biwenger) is None


def test_the_market_image_carries_the_fixture_column():
    from packages.biwenger_tools.api.logic import actions
    from packages.biwenger_tools.api.logic.orchestration import OrchestratorContext

    biwenger = MagicMock()
    biwenger.get_market_players.return_value = []
    ctx = OrchestratorContext(
        biwenger=biwenger, biwenger_players={}, jp_index={"by_name": {}, "by_slug": {}}
    )
    with (
        patch(_patches("build_context"), return_value=ctx),
        patch(_patches("require_telegram"), return_value=("tok", "chat")),
        patch(_patches("_send_image")),
        patch(_patches("read_fixture_runs"), return_value={}),
        patch(_patches("build_table_image"), return_value=b"") as mock_image,
    ):
        actions.run_market()
    assert mock_image.call_args.kwargs["extra_cols"] == ["Calendario (5)"]


def _teams_ctx():
    from packages.biwenger_tools.api.logic.orchestration import OrchestratorContext

    biwenger = MagicMock()
    biwenger.user_id = 1
    biwenger.get_league_users.return_value = {1: "Me", 2: "Rival"}
    biwenger.get_manager_squad.return_value = []
    biwenger.get_market_players.return_value = []
    return OrchestratorContext(
        biwenger=biwenger, biwenger_players={}, jp_index={"by_name": {}, "by_slug": {}}
    )


def _run_teams(manager_id):
    from packages.biwenger_tools.api.logic import actions

    ctx = _teams_ctx()
    with (
        patch(_patches("config")),
        patch(_patches("build_context"), return_value=ctx),
        patch(_patches("require_telegram"), return_value=("tok", "chat")),
        patch(_patches("_send_image")),
        patch(_patches("send_image_or_text_fallback"), return_value=True),
        patch(_patches("time")),
        patch(_patches("read_fixture_runs"), return_value={}) as mock_read,
        patch(_patches("build_table_image"), return_value=b"") as mock_image,
    ):
        actions.run_teams(manager_id)
    return {c.args[1]: c.kwargs.get("extra_cols") for c in mock_image.call_args_list}, (
        mock_read
    )


def test_every_squad_image_carries_the_fixture_column():
    cols, mock_read = _run_teams(None)
    assert cols["🛡️ Mi equipo"] == ["Calendario (5)"]
    assert cols["👤 Rival"] == ["Clausulable", "Cláusula", "Calendario (5)"]
    assert cols["🛒 Mercado"] == ["Calendario (5)"]
    mock_read.assert_called_once()


def test_a_single_squad_image_carries_the_fixture_column():
    assert _run_teams(1)[0] == {"🛡️ Mi equipo": ["Calendario (5)"]}
    assert _run_teams(2)[0] == {
        "👤 Rival": ["Clausulable", "Cláusula", "Calendario (5)"]
    }
