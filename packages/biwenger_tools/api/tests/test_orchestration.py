"""Unit tests for `logic/orchestration.py` — the Oráculo fallback in
`build_context()`.

`OraculoError` is the level-3 fallback from the Oráculo design: unreachable
or wrong, the read degrades to JP alone and the whole context still comes
back. Mocked at the boundary (`core.sdk.oraculo`, `core.sdk.jp`,
`BiwengerClient`) — nothing here touches the network.
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from core.sdk.oraculo import OraculoError
from packages.biwenger_tools.api.logic import orchestration
from packages.biwenger_tools.api.logic.player_matching import find_player_match


def _patch(name: str) -> str:
    return f"packages.biwenger_tools.api.logic.orchestration.{name}"


def _base_patches(stack: ExitStack) -> None:
    """Everything `build_context` needs before it gets to Oráculo."""
    stack.enter_context(patch(_patch("check_api_health")))
    stack.enter_context(patch(_patch("fetch_all_players"), return_value=[]))
    biwenger = MagicMock()
    biwenger.get_all_players_data_map.return_value = {}
    stack.enter_context(patch(_patch("build_biwenger_session"), return_value=biwenger))


PICKS_RESULT = {
    "matchday": 7,
    "generated_at": "2026-09-16T21:00:00+00:00",
    "model_tag": "test",
    "picks": {
        "delanteros": [
            {
                "playerId": 2,
                "playerName": "Punta",
                "slug": "punta-2",
                "predictedPoints": 7.4,
                "chance": 80,
            }
        ],
        "chollos": [],
    },
    "fixtures": [
        {"fixtureId": 1, "fixtureDate": "2026-09-18T18:00:00+00:00"},
    ],
}

PREDICTIONS = [
    {
        "playerId": 2,
        "playerName": "Punta",
        "slug": "punta-2",
        "predictedPoints": 7.4,
        "chance": 80,
        "fixtureDate": "2026-09-18T18:00:00+00:00",
    },
    {
        # A different matchday's row — must not leak into the index.
        "playerId": 3,
        "playerName": "Otra Jornada",
        "slug": "otra-3",
        "predictedPoints": 1.0,
        "chance": 50,
        "fixtureDate": "2026-09-25T18:00:00+00:00",
    },
]


def test_a_successful_read_builds_an_index_scoped_to_the_upcoming_matchday():
    with ExitStack() as stack:
        _base_patches(stack)
        stack.enter_context(patch(_patch("fetch_picks"), return_value=PICKS_RESULT))
        stack.enter_context(
            patch(_patch("fetch_predictions"), return_value=PREDICTIONS)
        )
        ctx = orchestration.build_context()

    assert ctx.oraculo_ok is True
    match = find_player_match("Punta", ctx.oraculo_index)
    assert match is not None
    assert match["_oraculo"]["predictedPoints"] == 7.4
    assert ctx.oraculo_index["lists_by_slug"]["punta-2"] == ["delanteros"]
    # The other matchday's player must not appear at all.
    assert find_player_match("Otra Jornada", ctx.oraculo_index) is None


def test_an_oraculo_error_leaves_the_index_empty_and_does_not_raise():
    """Level 3 of the design's fallback: unreachable or wrong must degrade to
    JP alone, never break the whole context."""
    with ExitStack() as stack:
        _base_patches(stack)
        stack.enter_context(
            patch(_patch("fetch_picks"), side_effect=OraculoError("boom"))
        )
        ctx = orchestration.build_context()

    assert ctx.oraculo_index == {}
    assert ctx.oraculo_ok is False


def test_an_oraculo_error_from_predictions_is_caught_too():
    with ExitStack() as stack:
        _base_patches(stack)
        stack.enter_context(patch(_patch("fetch_picks"), return_value=PICKS_RESULT))
        stack.enter_context(
            patch(_patch("fetch_predictions"), side_effect=OraculoError("boom"))
        )
        ctx = orchestration.build_context()

    assert ctx.oraculo_index == {}
    assert ctx.oraculo_ok is False


def test_a_shape_change_at_the_provider_is_caught_too():
    """The likely failure: the page still answers, in a shape we cannot read.

    `OraculoError` covers the network. A `KeyError` or `TypeError` out of the
    parsing would otherwise escape `build_context` and take the whole 09:00
    digest with it, for a provider that is meant to be optional.
    """
    with ExitStack() as stack:
        _base_patches(stack)
        stack.enter_context(
            patch(_patch("fetch_picks"), side_effect=KeyError("jugadores"))
        )
        ctx = orchestration.build_context()

    assert ctx.oraculo_index == {}
    assert ctx.oraculo_ok is False
