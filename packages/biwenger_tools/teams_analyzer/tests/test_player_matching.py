import pytest
from packages.biwenger_tools.teams_analyzer.logic.player_matching import (
    build_jp_index,
    find_player_match,
    normalize_name,
)


def _jp(name, slug=None, **extra):
    return {"name": name, "slug": slug or name.lower().replace(" ", "-"), **extra}


@pytest.fixture
def jp_index():
    players = [
        _jp("Oihan Sancet"),
        _jp("Javier Hernandez"),
        _jp("Vlachodimos"),
        _jp("Rahim"),
        _jp("Javi Rueda"),
        _jp("Brugui"),
        _jp("R. Rodriguez"),
        _jp("M. Moreno"),
        _jp("Espino"),
        _jp("Giuliano"),
        _jp("C. Vicente"),
        _jp("Cristian"),
        _jp("Jose Luis Morales"),
        _jp("Vini Jr", slug="vini-jr"),
    ]
    return build_jp_index(players)


def test_normalize_name():
    assert normalize_name("Oihan Sancet") == "oihan sancet"
    assert normalize_name("Javier HernáNDez ") == "javier hernandez"
    assert normalize_name("odysséas") == "odysseas"


def test_find_player_match_direct(jp_index):
    result = find_player_match("Oihan Sancet", jp_index)
    assert result["name"] == "Oihan Sancet"


def test_find_player_match_manual_mapping(jp_index):
    # "sancet" en Biwenger -> "oihan sancet" en JP via PLAYER_NAME_MAPPINGS
    result = find_player_match("Sancet", jp_index)
    assert result["name"] == "Oihan Sancet"

    # "vinicius jr" -> "vini jr"
    result = find_player_match("Vinicius Jr", jp_index)
    assert result["name"] == "Vini Jr"


def test_find_player_match_slug_fallback():
    players = [_jp("Vini Jr", slug="vinicius-junior")]
    idx = build_jp_index(players)
    result = find_player_match("vinicius-junior", idx)
    assert result["name"] == "Vini Jr"


def test_find_player_match_last_name(jp_index):
    result = find_player_match("Pacha Espino", jp_index)
    assert result["name"] == "Espino"


def test_find_player_match_first_name(jp_index):
    result = find_player_match("Giuliano Simeone", jp_index)
    assert result["name"] == "Giuliano"


def test_find_player_match_initial_last_name(jp_index):
    result = find_player_match("Carlos Vicente", jp_index)
    assert result["name"] == "C. Vicente"


def test_find_player_match_fallback_subset(jp_index):
    result = find_player_match("Morales", jp_index)
    assert result["name"] == "Jose Luis Morales"


def test_find_player_match_no_match(jp_index):
    assert find_player_match("Jugador Ficticio", jp_index) is None
