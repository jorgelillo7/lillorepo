"""Unit tests for the mineral-similarity engine."""

from packages.be_water.web.domain import Water, mineralization_label
from packages.be_water.web.similarity import (
    distance,
    favorites_centroid,
    profile_traits,
    recommend,
    recommend_nearby,
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


def test_profile_traits_words_the_strong_deviations():
    """A calcium-heavy, sodium-light centroid must be described as such —
    and near-median fields must stay unmentioned."""
    catalog = [
        _water(f"w{i}", tds=200 + i, na=20, province="X", community="Y")
        for i in range(6)
    ]
    for w in catalog:
        w.minerals.update({"calcium": 40, "magnesium": 10})
    centroid = {"tds": 210, "calcium": 90, "sodium": 4, "magnesium": 10.5}
    traits = profile_traits(centroid, catalog)
    assert "rica en calcio" in traits
    assert "muy baja en sodio" in traits
    assert all("magnesio" not in t for t in traits)  # ~median → silent


def test_profile_traits_needs_enough_catalog_coverage():
    """Fields observed in <5 waters can't define a median — no trait."""
    catalog = [_water("a", 200), _water("b", 220)]
    traits = profile_traits({"tds": 210, "calcium": 90}, catalog)
    assert traits == []


def test_distance_normalizes_by_shared_coverage():
    """A missing field must not make an otherwise-identical water look
    farther than a genuinely different one."""
    full = {"tds": 261, "sodium": 5, "calcium": 59, "magnesium": 25}
    same_minus_one = {"tds": 261, "sodium": 5, "calcium": 59}  # mg unknown
    different = {"tds": 900, "sodium": 200, "calcium": 10, "magnesium": 2}
    assert distance(full, same_minus_one) < distance(full, different)


# --- recommend_nearby (geo fallback, real adjacency) ------------------------


def test_recommend_nearby_pulls_from_adjacent_provinces():
    """Madrid has no bottled water of its own → recommend from bordering
    provinces. Segovia borders Madrid, so Bezoya (Segovia) is a candidate;
    Girona does not border Madrid, so Vichy is excluded."""
    catalog = [SOLAN, BEZOYA, VICHY]  # Cuenca, Segovia, Girona
    result = recommend_nearby([SOLAN], catalog, place="Madrid")
    ids = [w.id for w, _ in result]
    assert "bezoya" in ids
    assert "vichy" not in ids


def test_recommend_nearby_excludes_favorites():
    """A neighbour water that is already a favourite is not recommended back."""
    result = recommend_nearby([SOLAN, BEZOYA], [SOLAN, BEZOYA], place="Madrid")
    assert all(w.id != "bezoya" for w, _ in result)


def test_recommend_nearby_without_favorites_is_empty():
    assert recommend_nearby([], [SOLAN, BEZOYA], place="Madrid") == []


def test_recommend_nearby_empty_when_place_has_no_neighbours():
    """An island province (no land border) yields no neighbour candidates."""
    assert recommend_nearby([SOLAN], [BEZOYA], place="Illes Balears") == []


def test_a_place_whose_only_water_is_already_a_favorite_still_returns_it():
    """ "Where am I drinking" is not "show me something new". La Rioja's only
    catalogue water is Peñaclara; excluding favorites emptied the result and
    the neighbour fallback then offered Zaragoza, as if the province had
    none."""
    penaclara = _water("penaclara", 649, province="La Rioja", community="La Rioja")
    catalog = [penaclara, SOLAN, LIVIANA]

    results = recommend([penaclara, SOLAN], catalog, "La Rioja")

    assert [w.id for w, _ in results] == ["penaclara"]


def test_favorites_profile_ignores_the_one_unusual_favorite():
    """The mean is the centre of mass the recommender needs; it is the wrong
    thing to describe a taste with. Six waters near 20 mg/L of sulfates and
    one at 287 average to 60 — quadruple the catalogue median — and that one
    bottle became the first trait the page announced."""
    from packages.be_water.web.similarity import favorites_centroid, favorites_profile

    favorites = [
        Water(
            id=str(i),
            name=str(i),
            brand="",
            spring="",
            province="",
            community="",
            minerals={"tds": 250, "sulfates": v},
        )
        for i, v in enumerate([9.3, 14.0, 21.3, 23.2, 25.0, 39.1, 287.0])
    ]

    assert favorites_centroid(favorites)["sulfates"] > 55  # dragged by the 287
    assert favorites_profile(favorites)["sulfates"] == 23.2  # the typical one


def test_the_spread_shows_what_the_headline_class_cannot():
    """The class comes from the mean and one strong favorite cannot move it:
    six near 250 plus one at 649 still averages 305, still `débil`. The range
    is what says the collection is not uniform."""
    from packages.be_water.web.similarity import mineralization_spread

    favorites = [_water("a", 197), _water("b", 261), _water("c", 649)]

    assert mineralization_spread(favorites) == (197, 649)
    assert mineralization_label(sum([197, 261, 649]) / 3) == "débil"


def test_the_spread_is_none_without_declared_values():
    from packages.be_water.web.similarity import mineralization_spread

    blank = Water(
        id="x", name="x", brand="", spring="", province="", community="", minerals={}
    )
    assert mineralization_spread([blank]) is None
