"""Tests for `sf_of` — the shared SF reader used to rank, filter and price
rival clausulazo candidates — and for `gather_rivals` threading the Oráculo
blend into every squad it reads."""

from unittest.mock import MagicMock

from packages.biwenger_tools.api.logic import clausulazo_candidates as cands
from packages.biwenger_tools.api.logic.clausulazo_candidates import sf_of


def _jp(rate):
    return {"predict": [{"type": 2, "rate": rate}]}


def test_sf_of_prefers_the_blended_prediction_over_the_raw_jp_rate():
    """`sf_of` feeds ranking, affordability and pricing for clausulazo
    candidates. If it read the raw JP rate while the row displays the
    Oráculo blend, a candidate could be ranked, filtered or priced by a
    number nobody sees on the card — the same bug the photo table had."""
    row = {"jp_player": _jp(100), "custom_prediction": 250}
    assert sf_of(row) == 250


def test_sf_of_falls_back_to_the_raw_jp_rate_when_no_blend_ran():
    row = {"jp_player": _jp(180)}
    assert sf_of(row) == 180


def test_sf_of_is_zero_for_a_player_with_no_projection_at_all():
    assert sf_of({"jp_player": None}) == 0
    assert sf_of({}) == 0


def test_gather_rivals_threads_the_oraculo_blend_into_every_rival_squad(monkeypatch):
    """`gather_rivals` reads one rival squad at a time, in a loop — if the
    blend is threaded into some iterations and not others, two rivals in
    the same pool end up ranked on different scales.

    Ana's player projects lower on raw JP (300) than Beto's (350). Oráculo
    rates Ana's player highly and Beto's poorly; once both rivals are built
    with the same index and scale, the blend inverts the ranking and
    `pick_top_in_position` picks Ana's player instead of Beto's — the
    opposite of what raw JP alone would choose.
    """
    from packages.biwenger_tools.api.logic import custom_prediction as cp
    from packages.biwenger_tools.api.logic import rows as rows_mod
    from packages.biwenger_tools.api.logic.player_matching import build_jp_index

    def _jp_player(name, rate):
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

    monkeypatch.setattr(cands, "time", MagicMock())  # skip sleep

    biwenger = MagicMock()
    biwenger.user_id = 0
    biwenger.get_league_users.return_value = {1: "Ana", 2: "Beto"}
    biwenger.get_manager_squad.side_effect = lambda url, mgr_id: (
        [{"id": 1}] if mgr_id == 1 else [{"id": 2}]
    )
    biwenger_players = {
        1: {"id": 1, "name": "Gamma", "position": 3, "price": 1_000_000},
        2: {"id": 2, "name": "Delta", "position": 3, "price": 1_000_000},
    }
    jp_index = build_jp_index([_jp_player("Gamma", 300), _jp_player("Delta", 350)])
    oraculo_index = rows_mod.build_oraculo_index(
        [_oraculo("Gamma", 5.0), _oraculo("Delta", 1.0)]
    )
    scale = cp.ProjectionScale(
        oraculo=(1.0, 2.0, 3.0, 4.0, 5.0), jp=(100.0, 200.0, 300.0, 400.0, 500.0)
    )

    rivals = cands.gather_rivals(
        biwenger, biwenger_players, jp_index, oraculo_index, oraculo_scale=scale
    )

    target, in_position = cands.pick_top_in_position(rivals, preferred_position=3)
    assert target["name"] == "Gamma"
    assert in_position is True
