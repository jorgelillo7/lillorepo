"""Unit tests for the mineral-similarity engine."""

from packages.be_water.web.domain import Water, mineralization_label
from packages.be_water.web.similarity import (
    by_mineralization,
    distance,
    favorites_centroid,
    profile_traits,
    rank_by_centroid,
    similar_waters,
    waters_in_place,
    waters_near_place,
)


def _ranked(favorites, catalog, place):
    """The region listing as the route builds it: filter, then rank."""
    return rank_by_centroid(
        waters_in_place(catalog, place), favorites_centroid(favorites)
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


def test_place_filter_then_centroid_ranking():
    """Favorites = Solán → in Girona the pick must be Ribes (weak-medium
    profile), never Vichy despite both being from Girona."""
    catalog = [SOLAN, LIVIANA, BEZOYA, VICHY, RIBES]
    ids = [w.id for w in _ranked([SOLAN], catalog, "Girona")]
    assert ids[0] == "ribes"
    assert set(ids) == {"ribes", "vichy"}  # only Girona waters, all of them


def test_place_matches_community_too():
    catalog = [SOLAN, LIVIANA, BEZOYA, VICHY, RIBES]
    assert [w.id for w in _ranked([SOLAN], catalog, "Cataluña")][0] == "ribes"


def test_place_matching_ignores_accents_and_case():
    """A hand-typed or shared `?lugar=cadiz` must find Cádiz."""
    cadiz = _water("penafiel", 300, province="Cádiz", community="Andalucía")
    assert [w.id for w in waters_in_place([cadiz, SOLAN], "cadiz")] == ["penafiel"]
    assert [w.id for w in waters_in_place([cadiz, SOLAN], "ANDALUCIA")] == ["penafiel"]


def test_an_empty_place_matches_nothing():
    """`place_key("")` equals a blank community field, so an unguarded filter
    would answer an empty search with every water that has no community."""
    homeless = Water(
        id="neval", name="Neval", brand="", spring="", province="", community=""
    )
    assert waters_in_place([homeless, SOLAN], "") == []
    assert waters_in_place([homeless, SOLAN], "   ") == []


def test_the_region_listing_does_not_depend_on_who_asks():
    """The invariant the whole page rests on: the two orders are permutations
    of one another. Identity reorders a region, it never redraws it."""
    catalog = [SOLAN, LIVIANA, BEZOYA, VICHY, RIBES]
    region = waters_in_place(catalog, "Cataluña")
    # A strong-water taste: Vichy leads for this visitor, Ribes leads for
    # everyone else — same two waters either way.
    personalized = rank_by_centroid(region, favorites_centroid([VICHY]))
    neutral = by_mineralization(region)
    assert {w.id for w in personalized} == {w.id for w in neutral}
    assert [w.id for w in personalized] == ["vichy", "ribes"]
    assert [w.id for w in neutral] == ["ribes", "vichy"]


def test_neutral_order_is_weakest_first_with_unknown_tds_last():
    unknown = Water(
        id="sin-datos", name="Sin datos", brand="", spring="", province="", community=""
    )
    assert [w.id for w in by_mineralization([VICHY, unknown, BEZOYA, SOLAN])] == [
        "bezoya",
        "solan",
        "vichy",
        "sin-datos",
    ]


def test_a_water_too_sparse_to_rank_still_appears_last():
    """Dropping it is right for "aguas parecidas" and wrong for a list that
    claims to show a whole region."""
    sparse = Water(
        id="misteriosa",
        name="Misteriosa",
        brand="",
        spring="",
        province="Girona",
        community="Cataluña",
        minerals={"tds": 260},  # one field → incomparable with everyone
    )
    ids = [w.id for w in _ranked([SOLAN], [RIBES, sparse, VICHY], "Girona")]
    assert ids == ["ribes", "vichy", "misteriosa"]


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


# --- waters_near_place (real adjacency) -------------------------------------


def test_nearby_pulls_from_adjacent_provinces():
    """Madrid has no bottled water of its own. Segovia borders Madrid, so
    Bezoya is a candidate; Girona does not, so Vichy is excluded."""
    catalog = [SOLAN, BEZOYA, VICHY]  # Cuenca, Segovia, Girona
    ids = [w.id for w in waters_near_place(catalog, "Madrid")]
    assert "bezoya" in ids
    assert "vichy" not in ids


def test_nearby_excludes_the_places_own_waters():
    """The section answers "what else is around" — a Girona water is not
    "near Girona", it is Girona."""
    ids = [w.id for w in waters_near_place([RIBES, VICHY, SOLAN], "Girona")]
    assert "ribes" not in ids and "vichy" not in ids


def test_nearby_is_empty_when_the_place_has_no_neighbours():
    """An island province (no land border) yields no neighbour candidates."""
    assert waters_near_place([BEZOYA], "Illes Balears") == []


def test_nearby_works_for_a_community_not_only_a_province():
    """`adjacent_provinces` returns [] for every community, which silently
    emptied this section for half the selector. Segovia borders Madrid, so it
    is a neighbour of Comunidad de Madrid too."""
    catalog = [SOLAN, BEZOYA, VICHY]
    ids = [w.id for w in waters_near_place(catalog, "Comunidad de Madrid")]
    assert "bezoya" in ids
    assert "vichy" not in ids


def test_a_place_whose_only_water_is_already_a_favorite_still_returns_it():
    """ "Where am I drinking" is not "show me something new". La Rioja's only
    catalogue water is Peñaclara; excluding favorites emptied the result and
    the neighbour fallback then offered Zaragoza, as if the province had
    none."""
    penaclara = _water("penaclara", 649, province="La Rioja", community="La Rioja")
    catalog = [penaclara, SOLAN, LIVIANA]

    assert [w.id for w in _ranked([penaclara, SOLAN], catalog, "La Rioja")] == [
        "penaclara"
    ]


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
