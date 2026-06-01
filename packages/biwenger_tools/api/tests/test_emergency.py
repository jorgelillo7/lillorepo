"""Unit tests for `api/logic/emergency.py`.

Covers:
- `_recent_lost_players` — board parsing, 24h window, id vs name match.
- `_unique_positions` — outfield positions a loss list implies.
- `_weakest_outfield_position` — counts + DEF > MID > FWD tie-break.
- `_pick_target` — in-position first, fallback to top SF overall.
- `preview_clausulazo` end-to-end (0/1/multi-loss + selector cases +
  force_position / force_weakest entry points).
- `execute_clausulazo` notifies on success and on Biwenger 4xx.
"""

from unittest.mock import MagicMock, patch

import pytest

from packages.biwenger_tools.api.logic import emergency

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
    losses = emergency._recent_lost_players(
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
    losses = emergency._recent_lost_players(
        biwenger, players, my_manager_name="Lillo", now_epoch=1500
    )
    assert len(losses) == 1 and losses[0]["position_id"] == 2


def test_recent_lost_players_ignores_entries_older_than_24h():
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [_board_entry(date_epoch=10, from_id=99, player_id=42)]
    }
    players = {42: _bw_player(42, "Ana", position=2)}
    now = 10 + emergency.RECENT_CLAUSULAZO_WINDOW_SECONDS + 1
    losses = emergency._recent_lost_players(
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
    losses = emergency._recent_lost_players(
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
    losses = emergency._recent_lost_players(
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
        emergency._weakest_outfield_position(
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
    assert emergency._weakest_outfield_position(_squad(11, 12, 13), players) == 2


def test_weakest_outfield_position_full_squad_picks_def():
    """Full squad (all positions equal at the maximum) — DEF still wins
    because of the tie-break order; in practice this branch is rare."""
    players = {i: _bw_player(i, f"P{i}", position=(2 + (i % 3))) for i in range(0, 12)}
    assert emergency._weakest_outfield_position(_squad(*range(0, 12)), players) == 2


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
    target, note = emergency._pick_target(candidates, preferred_position=2)
    assert target["bw_id"] == 2
    assert note == ""


def test_pick_target_falls_back_to_top_sf_when_position_empty():
    candidates = [
        _cand(1, position=3, sf=400),
        _cand(2, position=4, sf=900),
    ]
    target, note = emergency._pick_target(candidates, preferred_position=2)
    assert target["bw_id"] == 2
    assert "Defensa" in note  # note mentions the position we couldn't fill


def test_pick_target_returns_none_when_no_candidates():
    target, note = emergency._pick_target([], preferred_position=2)
    assert target is None
    assert note == ""


# --- preview_clausulazo (end-to-end with mocks) --------------------------


def _patches(target):
    return f"packages.biwenger_tools.api.logic.emergency.{target}"


@pytest.fixture
def preview_env():
    """Wire `preview_clausulazo` collaborators: build_context, gather_rivals,
    filter_affordable, _send. Returns the mocks the test wants to assert on."""
    from contextlib import ExitStack

    def _enter(
        *,
        cash,
        my_squad,
        biwenger_players,
        rivals,
        affordable,
        losses=None,
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
        stack.enter_context(
            patch(_patches("_recent_lost_players"), return_value=losses or [])
        )
        stack.enter_context(patch(_patches("gather_rivals"), return_value=rivals))
        stack.enter_context(
            patch(_patches("filter_affordable"), return_value=affordable)
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
