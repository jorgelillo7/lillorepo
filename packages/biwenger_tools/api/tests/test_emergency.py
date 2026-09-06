"""Unit tests for `api/logic/emergency.py`.

Covers:
- `recent_lost_players` — board parsing, 24h window, id vs name match.
- `unique_outfield_positions` — outfield positions a loss list implies.
- `weakest_outfield_position` — counts + DEF > MID > FWD tie-break.
- `pick_top_in_position` — in-position first, fallback to top SF overall.
- `preview_clausulazo` end-to-end (0/1/multi-loss + selector cases +
  force_position / force_weakest entry points).
- `execute_clausulazo` notifies on success and on Biwenger 4xx.

Detection helpers live in `clausulazo_detection`; candidate scoring in
`clausulazo_candidates`. We import from the canonical home and patch the
re-imported names *inside* `emergency` when stubbing `preview_clausulazo`'s
collaborators, since that's where the lookup happens at runtime.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from packages.biwenger_tools.api.logic import (
    clausulazo_candidates,
    clausulazo_detection,
    emergency,
)
from packages.biwenger_tools.api.logic.orchestration import OrchestratorContext

# --- _recent_lost_players -----------------------------------------------


def _board_entry(date_epoch, from_id=None, from_name=None, player_id=42):
    return {
        "date": date_epoch,
        "content": [
            {
                "type": "clause",
                "from": {"id": from_id, "name": from_name},
                "player": {"id": player_id},
            }
        ],
    }


def _bw_player(player_id, name, position, alt=None):
    return {
        "id": player_id,
        "name": name,
        "position": position,
        "altPositions": alt or [],
        "price": 0,
    }


def test_recent_lost_players_matches_by_user_id():
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [_board_entry(1000, from_id=99, player_id=42)]
    }
    players = {42: _bw_player(42, "Ana", position=2)}
    losses = clausulazo_detection.recent_lost_players(
        biwenger, players, my_manager_name="anyone", now_epoch=1500
    )
    assert [(loss["name"], loss["position_id"]) for loss in losses] == [("Ana", 2)]


def test_recent_lost_players_matches_by_name_when_id_missing():
    """Board payload variants may omit `from.id` — fall back to name match."""
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [_board_entry(1000, from_name="Lillo", player_id=42)]
    }
    players = {42: _bw_player(42, "Ana", position=2)}
    losses = clausulazo_detection.recent_lost_players(
        biwenger, players, my_manager_name="Lillo", now_epoch=1500
    )
    assert len(losses) == 1 and losses[0]["position_id"] == 2


def test_recent_lost_players_ignores_entries_older_than_24h():
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [_board_entry(date_epoch=10, from_id=99, player_id=42)]
    }
    players = {42: _bw_player(42, "Ana", position=2)}
    now = 10 + clausulazo_detection.RECENT_CLAUSULAZO_WINDOW_SECONDS + 1
    losses = clausulazo_detection.recent_lost_players(
        biwenger, players, my_manager_name="x", now_epoch=now
    )
    assert losses == []


def test_recent_lost_players_returns_all_matches_including_multi_pos():
    """Multi-position losses are surfaced (so the selector can list
    them); the suppression rule lives in `preview_clausulazo`, not here."""
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [
            {
                "date": 1000,
                "content": [
                    {
                        "type": "clause",
                        "from": {"id": 99},
                        "player": {"id": 42},
                    },
                    {
                        "type": "clause",
                        "from": {"id": 99},
                        "player": {"id": 43},
                    },
                ],
            }
        ]
    }
    players = {
        42: _bw_player(42, "MultiGuy", position=2, alt=[3]),
        43: _bw_player(43, "SimpleGuy", position=4),
    }
    losses = clausulazo_detection.recent_lost_players(
        biwenger, players, my_manager_name="x", now_epoch=1500
    )
    assert [loss["name"] for loss in losses] == ["MultiGuy", "SimpleGuy"]
    assert losses[0]["alt_positions"] == [3]


def test_recent_lost_players_ignores_other_managers_losses():
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [_board_entry(1000, from_id=42, from_name="Otro", player_id=42)]
    }
    players = {42: _bw_player(42, "X", position=2)}
    losses = clausulazo_detection.recent_lost_players(
        biwenger, players, my_manager_name="Lillo", now_epoch=1500
    )
    assert losses == []


# --- _weakest_outfield_position ------------------------------------------


def _squad(*player_ids):
    return [{"id": pid} for pid in player_ids]


def test_weakest_outfield_position_picks_minimum_count():
    players = {
        10: _bw_player(10, "Gk", position=1),
        11: _bw_player(11, "D1", position=2),
        12: _bw_player(12, "D2", position=2),
        13: _bw_player(13, "D3", position=2),
        14: _bw_player(14, "M1", position=3),
        15: _bw_player(15, "M2", position=3),
        16: _bw_player(16, "F1", position=4),
    }
    # 3 DEF / 2 MID / 1 FWD → weakest is FWD.
    assert (
        clausulazo_detection.weakest_outfield_position(
            _squad(10, 11, 12, 13, 14, 15, 16), players
        )
        == 4
    )


def test_weakest_outfield_position_ties_prefer_def_then_mid():
    players = {
        11: _bw_player(11, "D1", position=2),
        12: _bw_player(12, "M1", position=3),
        13: _bw_player(13, "F1", position=4),
    }
    # 1 of each → DEF wins on tie-break.
    assert (
        clausulazo_detection.weakest_outfield_position(_squad(11, 12, 13), players) == 2
    )


def test_weakest_outfield_position_full_squad_picks_def():
    """Full squad (all positions equal at the maximum) — DEF still wins
    because of the tie-break order; in practice this branch is rare."""
    players = {i: _bw_player(i, f"P{i}", position=(2 + (i % 3))) for i in range(0, 12)}
    assert (
        clausulazo_detection.weakest_outfield_position(_squad(*range(0, 12)), players)
        == 2
    )


# --- _pick_target --------------------------------------------------------


def _cand(bw_id, position, sf, owner_user_id=7, owner="Pepe", clause=5_000_000):
    return {
        "bw_id": bw_id,
        "name": f"P{bw_id}",
        "position_id": position,
        "owner": owner,
        "owner_user_id": owner_user_id,
        "clause_value": clause,
        "jp_player": {"predict": [{"type": 2, "rate": sf}]},
    }


def test_pick_target_returns_top_sf_in_preferred_position():
    candidates = [
        _cand(1, position=2, sf=300),
        _cand(2, position=2, sf=500),
        _cand(3, position=4, sf=900),  # higher SF but wrong position
    ]
    target, in_preferred = clausulazo_candidates.pick_top_in_position(
        candidates, preferred_position=2
    )
    assert target["bw_id"] == 2
    assert in_preferred is True


def test_pick_target_falls_back_to_top_sf_when_position_empty():
    candidates = [
        _cand(1, position=3, sf=400),
        _cand(2, position=4, sf=900),
    ]
    target, in_preferred = clausulazo_candidates.pick_top_in_position(
        candidates, preferred_position=2
    )
    assert target["bw_id"] == 2
    assert in_preferred is False  # caller will build the "no DEF afford" note


def test_pick_target_returns_none_when_no_candidates():
    target, in_preferred = clausulazo_candidates.pick_top_in_position(
        [], preferred_position=2
    )
    assert target is None
    assert in_preferred is False


# --- preview_clausulazo (end-to-end with mocks) --------------------------


def _patches(target):
    return f"packages.biwenger_tools.api.logic.emergency.{target}"


def _legal_my_rows():
    """A minimal 3-4-3-shaped squad: enough to satisfy `composition_ok` so
    tests that are not about the rebuild trigger keep exercising the
    single-signing flow, exactly as before the trigger existed."""
    rows = [{"bw_id": 900, "name": "MyGk", "position_id": 1, "alt_positions": []}]
    rows += [
        {"bw_id": 901 + i, "name": f"MyDef{i}", "position_id": 2, "alt_positions": []}
        for i in range(3)
    ]
    rows += [
        {"bw_id": 911 + i, "name": f"MyMid{i}", "position_id": 3, "alt_positions": []}
        for i in range(4)
    ]
    rows += [
        {"bw_id": 921 + i, "name": f"MyFwd{i}", "position_id": 4, "alt_positions": []}
        for i in range(3)
    ]
    return rows


@pytest.fixture
def preview_env():
    """Wire `preview_clausulazo` collaborators: build_context, gather_rivals,
    filter_affordable, build_squad_rows, _send. Returns the mocks the test
    wants to assert on.

    `build_squad_rows` is patched to a legal-XI stand-in by default so every
    test not specifically about the rebuild trigger keeps satisfying
    `composition_ok` regardless of how small its `my_squad`/`biwenger_players`
    fixtures are (those still drive `weakest_outfield_position` and
    `recent_lost_players`, unaffected by this). Pass `my_rows=` to control it
    directly — the rebuild tests use this to force `composition_ok` False.
    """
    from contextlib import ExitStack

    def _enter(
        *,
        cash,
        my_squad,
        biwenger_players,
        rivals,
        affordable,
        losses=None,
        my_rows=None,
    ):
        stack = ExitStack()

        biwenger = MagicMock(user_id=99)
        biwenger.get_manager_squad.return_value = my_squad
        biwenger.get_account_state.return_value = {"cash": cash, "max_bid": cash}
        biwenger.get_league_users.return_value = {99: "Lillo"}

        from packages.biwenger_tools.api.logic.orchestration import (
            OrchestratorContext,
        )

        ctx = OrchestratorContext(
            biwenger=biwenger, biwenger_players=biwenger_players, jp_index={}
        )
        stack.enter_context(patch(_patches("build_context"), return_value=ctx))
        # The emergency module imports these names by short name from
        # their canonical homes (clausulazo_detection / candidates), so
        # patching the re-imported attribute on `emergency` is what
        # affects the lookup `preview_clausulazo` actually performs.
        stack.enter_context(
            patch(_patches("recent_lost_players"), return_value=losses or [])
        )
        stack.enter_context(patch(_patches("gather_rivals"), return_value=rivals))
        stack.enter_context(
            patch(_patches("filter_affordable"), return_value=affordable)
        )
        stack.enter_context(
            patch(
                _patches("build_squad_rows"),
                return_value=my_rows if my_rows is not None else _legal_my_rows(),
            )
        )
        # Rebuild-mode tests reach `rebuild.store`, a Firestore write — never
        # exercised by a test not specifically about the trigger, but stubbed
        # here so none of them accidentally reach a real client.
        stack.enter_context(
            patch.object(emergency.rebuild, "store", return_value="plan-test-id")
        )
        mock_send = stack.enter_context(patch(_patches("_send")))
        return biwenger, mock_send, stack

    with ExitStack() as outer:

        def factory(**kwargs):
            biwenger, mock_send, stack = _enter(**kwargs)
            outer.callback(stack.close)
            return biwenger, mock_send

        yield factory


def _loss(player_id, name, position, alt=None, date=1000):
    return {
        "player_id": player_id,
        "name": name,
        "position_id": position,
        "alt_positions": alt or [],
        "date": date,
    }


def test_preview_single_loss_targets_lost_line(preview_env):
    """One DEF lost (single-position) → targets DEF without selector."""
    biwenger_players = {
        10: _bw_player(10, "Gk", position=1),
        11: _bw_player(11, "D1", position=2),
    }
    rivals = [_cand(50, position=2, sf=500), _cand(51, position=4, sf=900)]
    biwenger, mock_send = preview_env(
        cash=10_000_000,
        my_squad=_squad(10, 11),
        biwenger_players=biwenger_players,
        rivals=rivals,
        affordable=rivals,
        losses=[_loss(42, "AnaDef", position=2)],
    )
    result = emergency.preview_clausulazo()

    assert result["target"]["player_id"] == 50  # DEF candidate wins, not the SF 900 FWD
    assert result["target"]["position_id"] == 2
    assert "AnaDef" in result["reason"]
    mock_send.assert_called_once()
    buttons = mock_send.call_args.kwargs["reply_markup"]["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "e:c:50:7:5000000"
    assert buttons[1]["callback_data"] == "e:n"


def test_preview_multi_pos_single_loss_shows_selector(preview_env):
    """One multi-pos loss → ambiguous → selector with both positions."""
    biwenger_players = {10: _bw_player(10, "Gk", position=1)}
    biwenger, mock_send = preview_env(
        cash=20_000_000,
        my_squad=_squad(10),
        biwenger_players=biwenger_players,
        rivals=[],
        affordable=[],
        losses=[_loss(42, "MultiGuy", position=2, alt=[3])],
    )
    result = emergency.preview_clausulazo()

    assert result.get("selector") is True
    assert result.get("target") is None  # no target yet, user has to choose
    text = mock_send.call_args.args[0]
    assert "MultiGuy" in text
    buttons_flat = [
        btn
        for row in mock_send.call_args.kwargs["reply_markup"]["inline_keyboard"]
        for btn in row
    ]
    callback_data = {b["callback_data"] for b in buttons_flat}
    assert "e:p:2" in callback_data  # DEF
    assert "e:p:3" in callback_data  # MID (alt)
    assert "e:m" in callback_data  # weakest fallback
    assert "e:n" in callback_data  # cancel


def test_preview_multiple_losses_shows_selector(preview_env):
    """Two single-position losses → can't tell which is more recent in
    the batched-date board → selector lists both."""
    biwenger, mock_send = preview_env(
        cash=20_000_000,
        my_squad=_squad(),
        biwenger_players={},
        rivals=[],
        affordable=[],
        losses=[
            _loss(42, "DefenderOne", position=2),
            _loss(43, "ForwardOne", position=4),
        ],
    )
    result = emergency.preview_clausulazo()

    assert result.get("selector") is True
    text = mock_send.call_args.args[0]
    assert "DefenderOne" in text and "ForwardOne" in text
    callbacks = {
        b["callback_data"]
        for row in mock_send.call_args.kwargs["reply_markup"]["inline_keyboard"]
        for b in row
    }
    assert {"e:p:2", "e:p:4", "e:m", "e:n"}.issubset(callbacks)


def test_preview_force_position_skips_detection(preview_env):
    """`force_position=3` jumps straight to picking a target in MID."""
    biwenger_players = {10: _bw_player(10, "Gk", position=1)}
    rivals = [_cand(50, position=3, sf=500), _cand(51, position=2, sf=900)]
    biwenger, mock_send = preview_env(
        cash=20_000_000,
        my_squad=_squad(10),
        biwenger_players=biwenger_players,
        rivals=rivals,
        affordable=rivals,
        losses=[_loss(42, "MultiGuy", position=2, alt=[3])],  # detection ignored
    )
    result = emergency.preview_clausulazo(force_position=3)

    assert result["target"]["player_id"] == 50  # MID candidate
    assert "elegido" in result["reason"]


def test_preview_force_weakest_skips_detection(preview_env):
    """`force_weakest=True` runs the weakest-line flow regardless of losses."""
    biwenger_players = {
        10: _bw_player(10, "Gk", position=1),
        11: _bw_player(11, "D1", position=2),
        12: _bw_player(12, "D2", position=2),
        13: _bw_player(13, "M1", position=3),
        14: _bw_player(14, "F1", position=4),
    }
    rivals = [_cand(50, position=3, sf=300), _cand(51, position=4, sf=600)]
    biwenger, mock_send = preview_env(
        cash=20_000_000,
        my_squad=_squad(10, 11, 12, 13, 14),
        biwenger_players=biwenger_players,
        rivals=rivals,
        affordable=rivals,
        losses=[_loss(42, "X", position=2)],  # detection ignored
    )
    result = emergency.preview_clausulazo(force_weakest=True)

    assert result["target"]["player_id"] == 50  # weakest = MID, no selector path
    assert "elegido" in result["reason"]


def test_preview_no_losses_uses_weakest_line(preview_env):
    biwenger_players = {
        10: _bw_player(10, "Gk", position=1),
        11: _bw_player(11, "D1", position=2),
        12: _bw_player(12, "D2", position=2),
        13: _bw_player(13, "M1", position=3),
        14: _bw_player(14, "F1", position=4),
    }
    rivals = [_cand(50, position=3, sf=300), _cand(51, position=4, sf=600)]
    biwenger, mock_send = preview_env(
        cash=20_000_000,
        my_squad=_squad(10, 11, 12, 13, 14),
        biwenger_players=biwenger_players,
        rivals=rivals,
        affordable=rivals,
        losses=[],
    )
    result = emergency.preview_clausulazo()

    assert result["target"]["player_id"] == 50  # the MID
    assert "más mermada" in result["reason"]


def test_two_goalkeeper_losses_are_reported_not_silently_dropped(preview_env):
    """Every recent loss being a goalkeeper must not fall through to
    `_reason_no_losses` — the last goalkeeper cannot be claused, so there is
    no line to reinforce, but the losses themselves are real."""
    biwenger, mock_send = preview_env(
        cash=20_000_000,
        my_squad=_squad(),
        biwenger_players={},
        rivals=[],
        affordable=[],
        losses=[
            _loss(10, "GkOne", position=1),
            _loss(11, "GkTwo", position=1),
        ],
    )
    result = emergency.preview_clausulazo()

    assert result.get("goalkeeper_only") is True
    assert mock_send.call_args.kwargs.get("reply_markup") is None
    text = mock_send.call_args.args[0]
    assert "GkOne" in text and "GkTwo" in text
    assert "sin clausulazos" not in text.lower()


def test_emergencia_never_targets_the_goalkeeper_line(preview_env):
    """A manager's own goalkeeper is exempt from `/emergencia` (the last one
    can never be claused), so a GK loss must resolve to the weakest outfield
    line instead of being treated as the line to reinforce."""
    biwenger_players = {
        10: _bw_player(10, "Gk", position=1),
        11: _bw_player(11, "D1", position=2),
        12: _bw_player(12, "D2", position=2),
        13: _bw_player(13, "M1", position=3),
        14: _bw_player(14, "F1", position=4),
    }
    rivals = [_cand(50, position=3, sf=300), _cand(51, position=4, sf=600)]
    biwenger, mock_send = preview_env(
        cash=20_000_000,
        my_squad=_squad(10, 11, 12, 13, 14),
        biwenger_players=biwenger_players,
        rivals=rivals,
        affordable=rivals,
        losses=[_loss(10, "MyGk", position=1)],
    )
    result = emergency.preview_clausulazo()

    assert result["target"]["position_id"] != 1
    assert result["target"]["player_id"] == 50  # weakest outfield line = MID
    assert "portero" in result["reason"].lower()


def test_preview_no_affordable_candidates_sends_no_target_message(preview_env):
    biwenger_players = {10: _bw_player(10, "Gk", position=1)}
    biwenger, mock_send = preview_env(
        cash=100_000,
        my_squad=_squad(10),
        biwenger_players=biwenger_players,
        rivals=[],
        affordable=[],
        losses=[],
    )
    result = emergency.preview_clausulazo()

    assert result["target"] is None
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs.get("reply_markup") is None
    assert "Sin candidatos" in mock_send.call_args.args[0]


# --- rebuild mode: the trigger and preview --------------------------------


def _broken_my_rows(defenders=0):
    """A squad missing enough defenders that no formation can be filled —
    every one of the 14 shapes needs at least 3 DEF (`rebuild._LINE_FLOOR`).
    """
    rows = [{"bw_id": 900, "name": "MyGk", "position_id": 1, "alt_positions": []}]
    rows += [
        {"bw_id": 901 + i, "name": f"MyDef{i}", "position_id": 2, "alt_positions": []}
        for i in range(defenders)
    ]
    rows += [
        {"bw_id": 911 + i, "name": f"MyMid{i}", "position_id": 3, "alt_positions": []}
        for i in range(6)
    ]
    rows += [
        {"bw_id": 921 + i, "name": f"MyFwd{i}", "position_id": 4, "alt_positions": []}
        for i in range(4)
    ]
    return rows


def _def_candidates(count=3, clause=5_000_000, sf=300):
    return [
        _cand(501 + i, position=2, sf=sf, clause=clause, owner_user_id=8, owner="Rival")
        for i in range(count)
    ]


def test_rebuild_mode_triggers_only_when_no_legal_xi_is_possible(preview_env):
    """A squad missing every defender cannot field any of the 14 formations
    (all need >=3 DEF), so `preview_clausulazo` must fork into the rebuild
    plan instead of the single-signing flow."""
    defenders = _def_candidates()
    biwenger, mock_send = preview_env(
        cash=30_000_000,
        my_squad=_squad(),
        biwenger_players={},
        rivals=defenders,
        affordable=defenders,
        losses=[],
        my_rows=_broken_my_rows(defenders=0),
    )
    result = emergency.preview_clausulazo()

    assert result.get("rebuild") is True
    assert result.get("plan_id")
    mock_send.assert_called_once()


def test_a_single_loss_that_still_fields_an_xi_keeps_the_one_player_flow(preview_env):
    """A squad that can still field a legal eleven (the default
    `_legal_my_rows` stand-in `preview_env` patches in) must keep going
    through the single-signing flow even with a recent loss — rebuild mode
    is for squads that cannot field an eleven at all, not for reacting to a
    single loss."""
    biwenger_players = {
        10: _bw_player(10, "Gk", position=1),
        11: _bw_player(11, "D1", position=2),
    }
    rivals = [_cand(50, position=2, sf=500), _cand(51, position=4, sf=900)]
    biwenger, mock_send = preview_env(
        cash=10_000_000,
        my_squad=_squad(10, 11),
        biwenger_players=biwenger_players,
        rivals=rivals,
        affordable=rivals,
        losses=[_loss(42, "AnaDef", position=2)],
    )
    result = emergency.preview_clausulazo()

    assert result.get("rebuild") is None
    assert result["target"]["player_id"] == 50
    assert result["target"]["position_id"] == 2


def test_rebuild_mode_takes_precedence_over_the_selector(preview_env):
    """Three losses would normally post the multi-loss selector, but a
    composition-broken squad must go straight to the rebuild plan instead —
    a selector asking which line to reinforce is meaningless when no single
    signing can restore an eleven."""
    defenders = _def_candidates()
    biwenger, mock_send = preview_env(
        cash=30_000_000,
        my_squad=_squad(),
        biwenger_players={},
        rivals=defenders,
        affordable=defenders,
        losses=[
            _loss(42, "DefenderOne", position=2),
            _loss(43, "ForwardOne", position=4),
            _loss(44, "MidOne", position=3),
        ],
        my_rows=_broken_my_rows(defenders=0),
    )
    result = emergency.preview_clausulazo()

    assert result.get("rebuild") is True
    assert result.get("selector") is None
    mock_send.assert_called_once()
    reply_markup = mock_send.call_args.kwargs.get("reply_markup")
    if reply_markup:
        callbacks = {
            b["callback_data"] for row in reply_markup["inline_keyboard"] for b in row
        }
        assert not any(cb.startswith("e:p:") or cb == "e:m" for cb in callbacks)


def test_the_preview_shows_the_eleven_the_plan_would_field(preview_env):
    """The message must show the eleven the plan would leave behind, proven
    with `xi_snapshot` over the projected squad rather than merely asserted.
    """
    my_rows = _broken_my_rows(defenders=0)  # GK1 + MID6 + FWD4, 0 DEF
    defenders = _def_candidates()
    biwenger, mock_send = preview_env(
        cash=30_000_000,
        my_squad=_squad(),
        biwenger_players={},
        rivals=defenders,
        affordable=defenders,
        losses=[],
        my_rows=my_rows,
    )
    result = emergency.preview_clausulazo()

    assert result["completes_xi"] is True
    text = mock_send.call_args.args[0]
    assert "Once resultante" in text
    assert "sigue sin poder formarse" not in text


# --- execute_rebuild -------------------------------------------------------


def _rebuild_signing(bw_id, line, reserved, clause_at_plan=None, owner_user_id=7):
    return {
        "bw_id": bw_id,
        "owner_user_id": owner_user_id,
        "line": line,
        "reserved": reserved,
        "clause_at_plan": clause_at_plan if clause_at_plan is not None else reserved,
    }


def _rebuild_doc(signings, created_at=None):
    return {
        "formation": "3-4-3",
        "cash_before": 40_000_000,
        "created_at": created_at if created_at is not None else time.time(),
        "signings": signings,
    }


def _pool_row(bw_id, line, clause, owner_user_id=8, owner="Rival", sf=300, name=None):
    return {
        "bw_id": bw_id,
        "name": name or f"P{bw_id}",
        "position_id": line,
        "alt_positions": [],
        "owner": owner,
        "owner_user_id": owner_user_id,
        "clause_value": clause,
        "jp_player": {"predict": [{"type": 2, "rate": sf}]},
    }


def _rebuild_ctx(cash=40_000_000):
    biwenger = MagicMock(user_id=99)
    biwenger.get_manager_squad.return_value = []
    biwenger.get_account_state.return_value = {"cash": cash}
    biwenger.place_clausulazo.return_value = {"id": 1, "status": "processed"}
    ctx = OrchestratorContext(biwenger=biwenger, biwenger_players={}, jp_index={})
    return biwenger, ctx


def test_execute_rebuild_refuses_a_plan_older_than_the_ttl():
    """Clause values move — a plan older than `REBUILD_PLAN_TTL_SECONDS` must
    be refused and discarded rather than executed against stale prices."""
    stale_created_at = time.time() - emergency.config.REBUILD_PLAN_TTL_SECONDS - 1
    doc = _rebuild_doc(
        [_rebuild_signing(111, line=2, reserved=5_000_000)], created_at=stale_created_at
    )
    with patch.object(emergency.rebuild, "load", return_value=doc), patch.object(
        emergency.rebuild, "discard"
    ) as mock_discard, patch(_patches("_send")) as mock_send, patch(
        _patches("build_context")
    ) as mock_build_context:
        result = emergency.execute_rebuild("plan1")

    assert result["status"] == "expired"
    mock_discard.assert_called_once_with("plan1")
    mock_build_context.assert_not_called()
    assert "caducado" in mock_send.call_args.args[0].lower()


def test_a_vanished_target_is_replaced_within_its_reserved_amount():
    """The stored target is gone from the fresh candidate pool; the
    replacement must come from the SAME line and cost no more than the SAME
    reserved amount — never a swap paid for out of another hole's budget."""
    doc = _rebuild_doc([_rebuild_signing(111, line=2, reserved=5_000_000)])
    replacement = _pool_row(222, line=2, clause=5_000_000, owner_user_id=9)
    biwenger, ctx = _rebuild_ctx()

    with patch.object(emergency.rebuild, "load", return_value=doc), patch.object(
        emergency.rebuild, "discard"
    ) as mock_discard, patch(_patches("_send")), patch(
        _patches("build_context"), return_value=ctx
    ), patch(
        _patches("gather_rivals"), return_value=[]
    ), patch(
        _patches("filter_affordable"), return_value=[replacement]
    ):
        result = emergency.execute_rebuild("plan1")

    biwenger.place_clausulazo.assert_called_once_with(
        player_id=222,
        amount=5_000_000,
        seller_user_id=9,
        offers_url=emergency.config.OFFERS_URL,
    )
    assert result["signings"][0]["swapped"] is True
    mock_discard.assert_called_once_with("plan1")


def test_nothing_outside_the_confirmed_plan_is_ever_bought():
    """Every `place_clausulazo` call must resolve to a player the stored
    plan actually targeted — never a tempting extra from the fresh pool,
    even one cheaper and better-value than the plan's own pick."""
    doc = _rebuild_doc(
        [
            _rebuild_signing(111, line=2, reserved=5_000_000),
            _rebuild_signing(222, line=3, reserved=6_000_000),
        ]
    )
    pool = [
        _pool_row(111, line=2, clause=5_000_000),
        _pool_row(222, line=3, clause=6_000_000),
        _pool_row(333, line=2, clause=1_000_000, sf=900),  # decoy: cheap, high value
        _pool_row(444, line=4, clause=1_000_000, sf=900),  # decoy: unrelated line
    ]
    biwenger, ctx = _rebuild_ctx()

    with patch.object(emergency.rebuild, "load", return_value=doc), patch.object(
        emergency.rebuild, "discard"
    ), patch(_patches("_send")), patch(
        _patches("build_context"), return_value=ctx
    ), patch(
        _patches("gather_rivals"), return_value=[]
    ), patch(
        _patches("filter_affordable"), return_value=pool
    ):
        emergency.execute_rebuild("plan1")

    bought_ids = {
        call.kwargs["player_id"] for call in biwenger.place_clausulazo.call_args_list
    }
    assert bought_ids == {111, 222}


def test_execution_reports_the_outcome_of_every_signing():
    """One outcome per stored signing — bought, swapped, or unfilled — never
    silently dropped."""
    doc = _rebuild_doc(
        [
            _rebuild_signing(111, line=2, reserved=5_000_000),
            _rebuild_signing(222, line=3, reserved=6_000_000),
            _rebuild_signing(333, line=4, reserved=4_000_000),
        ]
    )
    pools = [
        [_pool_row(111, line=2, clause=5_000_000)],  # bought as planned
        [_pool_row(999, line=3, clause=6_000_000)],  # target gone — swap
        [],  # nobody left at all — unfilled
    ]
    biwenger, ctx = _rebuild_ctx()

    with patch.object(emergency.rebuild, "load", return_value=doc), patch.object(
        emergency.rebuild, "discard"
    ), patch(_patches("_send")) as mock_send, patch(
        _patches("build_context"), return_value=ctx
    ), patch(
        _patches("gather_rivals"), return_value=[]
    ), patch(
        _patches("filter_affordable"), side_effect=pools
    ):
        result = emergency.execute_rebuild("plan1")

    statuses = [outcome["status"] for outcome in result["signings"]]
    assert statuses == ["bought", "bought", "unfilled"]
    assert result["signings"][1]["swapped"] is True
    text = mock_send.call_args.args[0]
    assert text.count("·") == 3


# --- execute_clausulazo --------------------------------------------------


def test_execute_clausulazo_calls_sdk_and_notifies():
    biwenger = MagicMock()
    biwenger.place_clausulazo.return_value = {"id": 777, "status": "processed"}
    biwenger.get_account_state.return_value = {"cash": 1_000_000}
    # The players map is consulted to resolve the name for the success
    # message — the callback only carries the player id.
    biwenger.get_all_players_data_map.return_value = {42: {"name": "Iago Aspas"}}
    with patch(_patches("build_biwenger_session"), return_value=biwenger), patch(
        _patches("_send")
    ) as mock_send:
        result = emergency.execute_clausulazo(
            player_id=42, owner_user_id=7, amount=5_000_000
        )

    biwenger.place_clausulazo.assert_called_once_with(
        player_id=42,
        amount=5_000_000,
        seller_user_id=7,
        offers_url=emergency.config.OFFERS_URL,
    )
    assert result["offer_id"] == 777
    assert result["cash_after"] == 1_000_000
    text = mock_send.call_args.args[0]
    assert "ejecutado" in text
    assert "Iago Aspas" in text


def test_execute_clausulazo_falls_back_to_id_when_player_missing_from_map():
    """Defensive: if the players map doesn't have the id (cache miss,
    new player, etc.), the message still goes out — just with the id."""
    biwenger = MagicMock()
    biwenger.place_clausulazo.return_value = {"id": 777, "status": "processed"}
    biwenger.get_account_state.return_value = {"cash": 1_000_000}
    biwenger.get_all_players_data_map.return_value = {}
    with patch(_patches("build_biwenger_session"), return_value=biwenger), patch(
        _patches("_send")
    ) as mock_send:
        emergency.execute_clausulazo(player_id=42, owner_user_id=7, amount=5_000_000)
    assert "jugador 42" in mock_send.call_args.args[0]


def test_execute_clausulazo_notifies_and_raises_on_failure():
    biwenger = MagicMock()
    biwenger.place_clausulazo.side_effect = RuntimeError("403 Clause locked")
    with patch(_patches("build_biwenger_session"), return_value=biwenger), patch(
        _patches("_send")
    ) as mock_send, pytest.raises(RuntimeError):
        emergency.execute_clausulazo(player_id=42, owner_user_id=7, amount=5_000_000)

    mock_send.assert_called_once()
    assert "rechazado" in mock_send.call_args.args[0]
