"""Unit tests for `api/logic/emergency.py`.

Covers:
- `_recent_lost_position` — board parsing, 24h window, multi-pos
  suppression, id vs name fallback.
- `_weakest_outfield_position` — counts + DEF > MID > FWD tie-break.
- `_pick_target` — in-position first, fallback to top SF overall.
- `preview_clausulazo` end-to-end with mocks (lost-line vs weakest-line
  flows, no-candidate path, multi-pos fallback).
- `execute_clausulazo` notifies on success and on Biwenger 4xx.
"""

from unittest.mock import MagicMock, patch

import pytest

from packages.biwenger_tools.api.logic import emergency

# --- _recent_lost_position -----------------------------------------------


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


def test_recent_lost_position_matches_by_user_id():
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [_board_entry(1000, from_id=99, player_id=42)]
    }
    players = {42: _bw_player(42, "Ana", position=2)}
    pos, name = emergency._recent_lost_position(
        biwenger, players, my_manager_name="anyone", now_epoch=1500
    )
    assert pos == 2 and name == "Ana"


def test_recent_lost_position_matches_by_name_when_id_missing():
    """Board payload variants may omit `from.id` — fall back to name match."""
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [_board_entry(1000, from_name="Lillo", player_id=42)]
    }
    players = {42: _bw_player(42, "Ana", position=2)}
    pos, _ = emergency._recent_lost_position(
        biwenger, players, my_manager_name="Lillo", now_epoch=1500
    )
    assert pos == 2


def test_recent_lost_position_ignores_entries_older_than_24h():
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [_board_entry(date_epoch=10, from_id=99, player_id=42)]
    }
    players = {42: _bw_player(42, "Ana", position=2)}
    now = 10 + emergency.RECENT_CLAUSULAZO_WINDOW_SECONDS + 1
    pos, name = emergency._recent_lost_position(
        biwenger, players, my_manager_name="x", now_epoch=now
    )
    assert pos is None and name is None


def test_recent_lost_position_suppresses_multi_position_player():
    """Multi-position loss is ambiguous → return None for position but
    keep the name so the message can mention the multi-pos fallback."""
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [_board_entry(1000, from_id=99, player_id=42)]
    }
    players = {42: _bw_player(42, "MultiGuy", position=2, alt=[3])}
    pos, name = emergency._recent_lost_position(
        biwenger, players, my_manager_name="x", now_epoch=1500
    )
    assert pos is None and name == "MultiGuy"


def test_recent_lost_position_takes_the_most_recent_match():
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [
            _board_entry(date_epoch=900, from_id=99, player_id=42),
            _board_entry(date_epoch=1000, from_id=99, player_id=43),
        ]
    }
    players = {
        42: _bw_player(42, "Old", position=2),
        43: _bw_player(43, "Recent", position=4),
    }
    pos, name = emergency._recent_lost_position(
        biwenger, players, my_manager_name="x", now_epoch=1500
    )
    assert pos == 4 and name == "Recent"


def test_recent_lost_position_ignores_other_managers_losses():
    biwenger = MagicMock(user_id=99)
    biwenger.get_all_clausulazos.return_value = {
        "data": [_board_entry(1000, from_id=42, from_name="Otro", player_id=42)]
    }
    players = {42: _bw_player(42, "X", position=2)}
    pos, _ = emergency._recent_lost_position(
        biwenger, players, my_manager_name="Lillo", now_epoch=1500
    )
    assert pos is None


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
        lost_position=(None, None),
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
            patch(_patches("_recent_lost_position"), return_value=lost_position)
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


def test_preview_recent_clausulazo_targets_lost_line(preview_env):
    """If a DEF was clausulated against me, the preview targets a DEF."""
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
        lost_position=(2, "AnaDef"),
    )
    result = emergency.preview_clausulazo()

    assert result["target"]["player_id"] == 50  # DEF candidate wins, not the SF 900 FWD
    assert result["target"]["position_id"] == 2
    assert "AnaDef" in result["reason"]
    # Telegram was called once with an inline keyboard carrying the 3 ids.
    mock_send.assert_called_once()
    kwargs = mock_send.call_args.kwargs
    assert "AnaDef" in mock_send.call_args.args[0]
    buttons = kwargs["reply_markup"]["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "e:c:50:7:5000000"
    assert buttons[1]["callback_data"] == "e:n"


def test_preview_multi_pos_loss_falls_back_to_weakest_line(preview_env):
    """`_recent_lost_position` returned `(None, "MultiGuy")` → use weakest line."""
    biwenger_players = {
        10: _bw_player(10, "Gk", position=1),
        11: _bw_player(11, "D1", position=2),
        12: _bw_player(12, "M1", position=3),
        13: _bw_player(13, "M2", position=3),
        14: _bw_player(14, "F1", position=4),
        15: _bw_player(15, "F2", position=4),
    }
    # squad: 1 GK / 1 DEF / 2 MID / 2 FWD → weakest outfield = DEF (count 1).
    rivals = [_cand(50, position=2, sf=400), _cand(51, position=3, sf=900)]
    biwenger, mock_send = preview_env(
        cash=20_000_000,
        my_squad=_squad(10, 11, 12, 13, 14, 15),
        biwenger_players=biwenger_players,
        rivals=rivals,
        affordable=rivals,
        lost_position=(None, "MultiGuy"),
    )
    result = emergency.preview_clausulazo()

    # DEF candidate is picked even though the MID has higher SF.
    assert result["target"]["player_id"] == 50
    assert "MultiGuy" in result["reason"]
    assert "multiposición" in result["reason"]


def test_preview_no_recent_clausulazo_uses_weakest_line(preview_env):
    biwenger_players = {
        10: _bw_player(10, "Gk", position=1),
        11: _bw_player(11, "D1", position=2),
        12: _bw_player(12, "D2", position=2),
        13: _bw_player(13, "M1", position=3),
        14: _bw_player(14, "F1", position=4),
    }
    # 2 DEF / 1 MID / 1 FWD → tie at 1 between MID and FWD → MID wins.
    rivals = [_cand(50, position=3, sf=300), _cand(51, position=4, sf=600)]
    biwenger, mock_send = preview_env(
        cash=20_000_000,
        my_squad=_squad(10, 11, 12, 13, 14),
        biwenger_players=biwenger_players,
        rivals=rivals,
        affordable=rivals,
        lost_position=(None, None),
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
        lost_position=(None, None),
    )
    result = emergency.preview_clausulazo()

    assert result["target"] is None
    mock_send.assert_called_once()
    # No inline keyboard when there's nothing to confirm.
    assert mock_send.call_args.kwargs.get("reply_markup") is None
    assert "Sin candidatos" in mock_send.call_args.args[0]


# --- execute_clausulazo --------------------------------------------------


def test_execute_clausulazo_calls_sdk_and_notifies():
    biwenger = MagicMock()
    biwenger.place_clausulazo.return_value = {"id": 777, "status": "processed"}
    biwenger.get_account_state.return_value = {"cash": 1_000_000}
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


def test_execute_clausulazo_notifies_and_raises_on_failure():
    biwenger = MagicMock()
    biwenger.place_clausulazo.side_effect = RuntimeError("403 Clause locked")
    with patch(_patches("build_biwenger_session"), return_value=biwenger), patch(
        _patches("_send")
    ) as mock_send, pytest.raises(RuntimeError):
        emergency.execute_clausulazo(player_id=42, owner_user_id=7, amount=5_000_000)

    mock_send.assert_called_once()
    assert "rechazado" in mock_send.call_args.args[0]
