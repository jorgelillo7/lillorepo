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
        {
            "bw_id": 10,
            "position_id": 3,
            "price": 7_400_000,
            "jp_player": {"predict": [{"type": 2, "rate": 538}]},
        },
        # Signed, not in JP yet.
        {"bw_id": 11, "position_id": 3, "price": 2_200_000, "jp_player": None},
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


def test_the_projection_ranks_the_best_eleven_not_the_whole_squad():
    """Only the eleven scores. Summing every player rewarded the manager
    with eighteen over the one with a better eleven and fourteen."""
    summary = {
        "Muchos": {**_squad(90_000_000, 8000), "eleven": 5000, "size": 18},
        "Mejor once": {**_squad(60_000_000, 6500), "eleven": 5500, "size": 14},
    }

    text = league_compare.render(summary, "t")

    assert text.index("Mejor once</b> — 5.500") < text.index("Muchos</b> — 5.000")
    assert "mejor once" in text.lower()
    assert "plantilla 8.000" in text


def test_collect_measures_each_squad_best_eleven():
    from unittest.mock import MagicMock, patch

    biwenger = MagicMock()
    biwenger.get_league_users.return_value = {1: "Jorge"}
    biwenger.get_manager_squad.return_value = [{"id": 10}]
    ctx = MagicMock(biwenger=biwenger, biwenger_players={}, jp_index={})
    target = "packages.biwenger_tools.api.logic.league_compare"
    with (
        patch(f"{target}.build_squad_rows", return_value=[{"price": 1}]),
        patch(f"{target}.xi_snapshot", return_value={"total_sf": 4321}),
    ):
        league_compare.reset_cache()
        summary = league_compare.collect(ctx)
        league_compare.reset_cache()

    assert summary["Jorge"]["eleven"] == 4321


def test_a_squad_that_cannot_field_an_eleven_ranks_at_zero():
    from unittest.mock import MagicMock, patch

    biwenger = MagicMock()
    biwenger.get_league_users.return_value = {1: "Jorge"}
    biwenger.get_manager_squad.return_value = []
    ctx = MagicMock(biwenger=biwenger, biwenger_players={}, jp_index={})
    target = "packages.biwenger_tools.api.logic.league_compare"
    with (
        patch(f"{target}.build_squad_rows", return_value=[]),
        patch(f"{target}.xi_snapshot", return_value=None),
    ):
        league_compare.reset_cache()
        summary = league_compare.collect(ctx)
        league_compare.reset_cache()

    assert summary["Jorge"]["eleven"] == 0


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


# --- public league info: /saldos and /movimientos for allowlisted members ---

_FIGURES = {
    "rows": [{"name": "A", "cash": 1, "max_bid": 2, "in_clauses": 0}],
    "notes": ["✅ ok"],
    "self_check_ok": True,
    "board_entries": 3,
    "unknown_types": [],
    "archive_lost": 0,
}


def _public_cash(is_member=True, cached=None, raises=None):
    from packages.biwenger_tools.api.logic import actions

    get_or_read = (
        {"side_effect": raises}
        if raises
        else {"return_value": cached if cached is not None else _FIGURES}
    )
    with (
        patch(_patches("public_members_store.is_member"), return_value=is_member),
        patch(_patches("public_cache.get_or_read"), **get_or_read),
        patch(_patches("build_cash_image"), return_value=b"png") as image,
        patch(_patches("send_telegram_photo_or_raise")) as photo,
        patch(_patches("send_telegram_message")) as text,
    ):
        result = actions.run_public_league_cash("777")
    return result, image, photo, text


def test_public_league_cash_goes_to_the_asking_chat():
    result, _, photo, _ = _public_cash()
    assert result == {"sent": 1}
    assert photo.call_args.args[1] == "777"


def test_public_league_cash_draws_no_exposure_block():
    _, image, _, _ = _public_cash()
    assert not image.call_args.kwargs.get("exposure")


def test_public_league_cash_failure_says_unavailable():
    from packages.biwenger_tools.api.logic import public_cache

    result, _, photo, text = _public_cash(
        raises=public_cache.Unavailable("league_cash")
    )
    photo.assert_not_called()
    sent = text.call_args.kwargs
    assert sent["chat_id"] == "777"
    assert "no disponible" in sent["text"]
    assert "league_cash" not in sent["text"]
    assert result["unavailable"] is True


def test_public_league_cash_refuses_a_non_member():
    result, _, photo, text = _public_cash(is_member=False)
    assert result["sent"] == 0
    photo.assert_not_called()
    text.assert_not_called()


def _owner_cash():
    from unittest.mock import MagicMock

    from packages.biwenger_tools.api.logic import actions

    ctx = MagicMock()
    ctx.biwenger.user_id = 1
    with (
        patch(_patches("require_telegram"), return_value=("tok", "chat")),
        patch(_patches("build_context"), return_value=ctx),
        patch(
            _patches("_cash_figures"), return_value=(_FIGURES, {1: []}, [])
        ) as figures,
        patch(_patches("_my_clause_rows"), return_value=[]),
        patch(_patches("league_cash.exposed"), return_value=[{"name": "x"}]),
        patch(_patches("league_cash.exposure_rows"), return_value=[{"name": "x"}]),
        patch(_patches("pact_store.load"), return_value=set()),
        patch(_patches("public_cache.refresh")) as refresh,
        patch(_patches("public_cache.get_or_read")) as cached,
        patch(_patches("build_cash_image"), return_value=b"png") as image,
        patch(_patches("send_telegram_photo_or_raise")),
    ):
        actions.run_league_cash()
    return figures, refresh, cached, image


def test_owner_league_cash_keeps_the_exposure_block():
    _, _, _, image = _owner_cash()
    assert image.call_args.kwargs["exposure"]


def test_owner_league_cash_always_reads_fresh_and_refreshes_the_cache():
    figures, refresh, cached, _ = _owner_cash()
    figures.assert_called_once()
    cached.assert_not_called()
    refresh.assert_called_once_with("league_cash", _FIGURES)


def test_movements_stop_reading_at_the_window():
    from unittest.mock import MagicMock

    from packages.biwenger_tools.api.logic import actions

    now = 1_800_000_000
    page = [{"type": "transfer", "date": now - i * 3600} for i in range(50)]
    biwenger = MagicMock()
    biwenger.get_board_messages.return_value = {"data": page}
    entries = actions._board_since(biwenger, now - 24 * 3600)
    biwenger.get_board_messages.assert_called_once()
    assert len(entries) == 50


def test_movements_read_is_cached(monkeypatch):
    from packages.biwenger_tools.api.logic import actions, public_cache
    from packages.biwenger_tools.api.tests.test_public_cache import _FakeStore

    store = _FakeStore()
    monkeypatch.setattr(public_cache, "_claim", store.claim)
    monkeypatch.setattr(public_cache, "_write", store.write)
    reads = []
    with (
        patch(_patches("public_members_store.is_member"), return_value=True),
        patch(
            _patches("_read_public_movements"),
            side_effect=lambda: reads.append(1) or [],
        ),
        patch(_patches("send_telegram_message_or_raise")),
    ):
        actions.run_public_movements("777")
        actions.run_public_movements("777")
    assert reads == [1]


def test_public_members_are_named_from_the_draft_registry():
    from packages.biwenger_tools.api.logic import actions

    with (
        patch(_patches("public_members_store.load"), return_value={279708352, 5}),
        patch(_patches("public_members_store.load_names"), return_value={}),
        patch(_patches("public_members_store.load_pending"), return_value={}),
        patch(
            _patches("draft_names_by_telegram_id"),
            return_value={279708352: "Manu"},
        ),
    ):
        result = actions.list_public_members()
    assert result == {
        "members": [5, 279708352],
        "names": {"279708352": "Manu"},
        "pending": {},
    }


def test_a_name_given_by_hand_wins_over_the_draft():
    from packages.biwenger_tools.api.logic import actions

    with (
        patch(_patches("public_members_store.load"), return_value={7}),
        patch(_patches("public_members_store.load_names"), return_value={7: "Primo"}),
        patch(_patches("public_members_store.load_pending"), return_value={}),
        patch(_patches("draft_names_by_telegram_id"), return_value={7: "Manu"}),
    ):
        assert actions.list_public_members()["names"] == {"7": "Primo"}


def test_a_draft_registry_that_cannot_be_read_costs_only_the_names():
    from packages.biwenger_tools.api.logic import actions

    with (
        patch(_patches("public_members_store.load"), return_value={7}),
        patch(_patches("public_members_store.load_names"), return_value={}),
        patch(_patches("public_members_store.load_pending"), return_value={}),
        patch(_patches("draft_names_by_telegram_id"), side_effect=RuntimeError),
    ):
        assert actions.list_public_members() == {
            "members": [7],
            "names": {},
            "pending": {},
        }


def test_an_unknown_chat_is_remembered_for_the_owner_to_authorize():
    from packages.biwenger_tools.api.logic import actions

    with (
        patch(_patches("public_members_store.is_member"), return_value=False),
        patch(_patches("public_members_store.remember_pending")) as remember,
    ):
        assert actions.check_public_chat("-100123", "Grupo Manu") == {"allowed": False}
    remember.assert_called_once_with(-100123, "Grupo Manu")


def test_a_member_chat_passes_the_gate_and_is_not_remembered():
    from packages.biwenger_tools.api.logic import actions

    with (
        patch(_patches("public_members_store.is_member"), return_value=True),
        patch(_patches("public_members_store.remember_pending")) as remember,
    ):
        assert actions.check_public_chat("-100123", "x") == {"allowed": True}
    remember.assert_not_called()


# --- public /analizar: the rivals, never the owner's team ---


def test_public_analizar_lists_only_rivals():
    from packages.biwenger_tools.api.logic import actions

    managers = {
        "managers": [
            {"id": 1, "name": "Jorge", "is_me": True},
            {"id": 2, "name": "Manu", "is_me": False},
        ]
    }
    with (
        patch(_patches("public_members_store.is_member"), return_value=True),
        patch(
            _patches("public_cache.get_or_read"),
            side_effect=lambda key, read: read(),
        ),
        patch(_patches("list_managers"), return_value=managers),
    ):
        result = actions.list_public_managers("-100")
    assert result == {"managers": [{"id": 2, "name": "Manu"}]}


def test_public_analizar_never_shows_the_owner_team():
    from packages.biwenger_tools.api.logic import actions

    with (
        patch(_patches("public_members_store.is_member"), return_value=True),
        patch(
            _patches("list_public_managers"),
            return_value={"managers": [{"id": 2, "name": "Manu"}]},
        ),
        patch(_patches("public_cache.get_or_read")) as cached,
        patch(_patches("send_telegram_photo_or_raise")) as photo,
    ):
        result = actions.run_public_team("-100", 1)
    assert result["sent"] == 0
    cached.assert_not_called()
    photo.assert_not_called()


def test_public_analizar_sends_a_rival_to_the_asking_chat_cached_per_manager():
    from packages.biwenger_tools.api.logic import actions

    with (
        patch(_patches("public_members_store.is_member"), return_value=True),
        patch(
            _patches("list_public_managers"),
            return_value={"managers": [{"id": 2, "name": "Manu"}]},
        ),
        patch(
            _patches("public_cache.get_or_read"),
            return_value={"png": b"png", "title": "👤 Manu"},
        ) as cached,
        patch(_patches("send_telegram_photo_or_raise")) as photo,
    ):
        result = actions.run_public_team("-100", 2)
    assert result == {"sent": 1}
    assert cached.call_args.args[0] == "team:2"
    assert photo.call_args.args[1] == "-100"


def test_public_analizar_refuses_a_non_member():
    from packages.biwenger_tools.api.logic import actions

    with (
        patch(_patches("public_members_store.is_member"), return_value=False),
        patch(_patches("send_telegram_photo_or_raise")) as photo,
    ):
        assert actions.run_public_team("-100", 2)["sent"] == 0
    photo.assert_not_called()
