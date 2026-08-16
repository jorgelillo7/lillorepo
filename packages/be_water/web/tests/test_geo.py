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


def test_adjacent_places_covers_communities_as_well_as_provinces():
    """`adjacent_provinces` answers [] for every community, so a
    community-level search had no neighbours at all — half the selector."""
    neighbors = geo.adjacent_places("Comunidad Valenciana")
    assert "Teruel" in neighbors  # borders Castellón
    assert "Murcia" in neighbors  # borders Alicante
    # Its own provinces are not its neighbours.
    assert "Valencia" not in neighbors and "Castellón" not in neighbors


def test_adjacent_places_still_answers_for_a_plain_province():
    assert geo.adjacent_places("Madrid") == geo.adjacent_provinces("Madrid")


def test_adjacent_places_is_accent_insensitive():
    assert "Teruel" in geo.adjacent_places("comunidad valenciana")


def test_a_name_that_is_both_province_and_community_agrees_with_itself():
    """La Rioja, Navarra, Asturias, Cantabria and Illes Balears are both. The
    two code paths must not disagree about their neighbours."""
    for place in ("La Rioja", "Navarra", "Asturias", "Cantabria"):
        assert geo.adjacent_places(place) == sorted(geo.adjacent_provinces(place))


def test_islands_and_unknown_places_have_no_neighbouring_places():
    assert geo.adjacent_places("Illes Balears") == []
    assert geo.adjacent_places("Canarias") == []
    assert geo.adjacent_places("Mordor") == []
    assert geo.adjacent_places("") == []


def test_every_province_has_a_community():
    for province in geo.ALL_PROVINCES:
        assert geo.community_of(province), f"sin comunidad: {province}"


def test_community_lookup_handles_aliases_and_accents():
    assert geo.community_of("Girona") == "Cataluña"
    assert geo.community_of("gerona") == "Cataluña"  # pre-normalization name
    assert geo.community_of("Baleares") == "Illes Balears"  # AESAN spelling
    assert geo.community_of("albacete") == "Castilla-La Mancha"
    assert geo.community_of("Marte") == ""
