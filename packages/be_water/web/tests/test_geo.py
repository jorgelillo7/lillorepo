"""Integrity of the province-adjacency map."""

from packages.be_water.web import geo
from packages.be_water.web.seed_data import SEED_WATERS


def test_adjacency_is_symmetric():
    """If A borders B, B must border A — catches typos in the map."""
    for province, neighbors in geo.PROVINCE_ADJACENCY.items():
        for neighbor in neighbors:
            assert neighbor in geo.PROVINCE_ADJACENCY, f"unknown: {neighbor}"
            assert (
                province in geo.PROVINCE_ADJACENCY[neighbor]
            ), f"{province} → {neighbor} is not symmetric"


def test_no_province_borders_itself():
    for province, neighbors in geo.PROVINCE_ADJACENCY.items():
        assert province not in neighbors


def test_every_seed_province_is_mapped():
    """Seed spellings must match the map or the fallback silently misses."""
    provinces = {raw["province"] for raw in SEED_WATERS if raw.get("province")}
    for province in provinces:
        assert province in geo.PROVINCE_ADJACENCY, f"unmapped: {province}"


def test_lookup_is_accent_insensitive():
    assert "Burgos" in geo.adjacent_provinces("alava")
    assert "Segovia" in geo.adjacent_provinces("Madrid")


def test_unknown_and_island_places_have_no_neighbors():
    assert geo.adjacent_provinces("Comunidad Valenciana") == []
    assert geo.adjacent_provinces("Illes Balears") == []


def test_every_province_has_a_community():
    for province in geo.ALL_PROVINCES:
        assert geo.community_of(province), f"sin comunidad: {province}"


def test_community_lookup_handles_aliases_and_accents():
    assert geo.community_of("Girona") == "Cataluña"
    assert geo.community_of("gerona") == "Cataluña"  # pre-normalization name
    assert geo.community_of("Baleares") == "Illes Balears"  # AESAN spelling
    assert geo.community_of("albacete") == "Castilla-La Mancha"
    assert geo.community_of("Marte") == ""
