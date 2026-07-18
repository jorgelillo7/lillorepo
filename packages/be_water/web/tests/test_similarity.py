"""Unit tests for the mineral-similarity engine."""

from packages.be_water.web.domain import Water, mineralization_label
from packages.be_water.web.similarity import (
    distance,
    favorites_centroid,
    recommend,
    similar_waters,
)


def _water(wid, tds, na=5, province="Cuenca", community="Castilla-La Mancha"):
    return Water(
        id=wid,
        name=wid,
        brand=wid,
        spring="",
        province=province,
        community=community,
        minerals={"tds": tds, "sodium": na, "calcium": tds * 0.2},
    )


SOLAN = _water("solan", 261)
LIVIANA = _water("liviana", 285)
BEZOYA = _water("bezoya", 27, na=1, province="Segovia", community="Castilla y León")
VICHY = _water("vichy", 3052, na=1110, province="Girona", community="Cataluña")
RIBES = _water("ribes", 208, na=3, province="Girona", community="Cataluña")


def test_mineralization_labels():
    assert mineralization_label(27) == "muy débil"
    assert mineralization_label(261) == "débil"
    assert mineralization_label(900) == "fuerte"
    assert mineralization_label(3052) == "muy fuerte"
    assert mineralization_label(None) == "desconocida"


def test_distance_orders_by_profile_not_absolute_gap():
    """Solán (261) must be closer to Liviana (285) than to Bezoya (27),
    and Vichy must be far from everything still."""
    assert distance(SOLAN.minerals, LIVIANA.minerals) < distance(
        SOLAN.minerals, BEZOYA.minerals
    )
    assert distance(SOLAN.minerals, LIVIANA.minerals) < distance(
        SOLAN.minerals, VICHY.minerals
    )


def test_similar_waters_excludes_self_and_sorts():
    catalog = [SOLAN, LIVIANA, BEZOYA, VICHY]
    result = similar_waters(SOLAN, catalog, top_n=3)
    ids = [w.id for w, _ in result]
    assert "solan" not in ids
    assert ids[0] == "liviana"


def test_recommend_filters_by_place_and_ranks_by_centroid():
    """Favorites = Solán → in Girona the pick must be Ribes (weak-medium
    profile), never Vichy despite both being from Girona."""
    catalog = [SOLAN, LIVIANA, BEZOYA, VICHY, RIBES]
    result = recommend([SOLAN], catalog, place="Girona")
    ids = [w.id for w, _ in result]
    assert ids[0] == "ribes"
    assert set(ids) <= {"ribes", "vichy"}  # only Girona waters


def test_recommend_matches_community_too():
    catalog = [SOLAN, LIVIANA, BEZOYA, VICHY, RIBES]
    result = recommend([SOLAN], catalog, place="Cataluña")
    assert [w.id for w, _ in result][0] == "ribes"


def test_recommend_without_favorites_is_empty():
    assert recommend([], [SOLAN, RIBES], place="Girona") == []


def test_centroid_averages_fields():
    centroid = favorites_centroid([SOLAN, LIVIANA])
    assert centroid["tds"] == (261 + 285) / 2


def test_sparse_waters_are_not_comparable():
    """Two waters sharing fewer than MIN_SHARED_FIELDS fields must never
    look 'similar' just because their missing fields match as zeros."""
    import math

    sparse_a = {"tds": 200}
    sparse_b = {"tds": 201, "sodium": 5}
    assert distance(sparse_a, sparse_b) == math.inf


def test_similar_waters_excludes_incomparable_entries():
    sparse = Water(
        id="misteriosa",
        name="Misteriosa",
        brand="?",
        spring="",
        province="Lugo",
        community="Galicia",
        minerals={"tds": 260},  # single field → incomparable with everyone
    )
    catalog = [SOLAN, LIVIANA, BEZOYA, sparse]
    ids = [w.id for w, _ in similar_waters(SOLAN, catalog, top_n=3)]
    assert "misteriosa" not in ids


def test_distance_normalizes_by_shared_coverage():
    """A missing field must not make an otherwise-identical water look
    farther than a genuinely different one."""
    full = {"tds": 261, "sodium": 5, "calcium": 59, "magnesium": 25}
    same_minus_one = {"tds": 261, "sodium": 5, "calcium": 59}  # mg unknown
    different = {"tds": 900, "sodium": 200, "calcium": 10, "magnesium": 2}
    assert distance(full, same_minus_one) < distance(full, different)
