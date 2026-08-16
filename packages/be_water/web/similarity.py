"""Mineral-profile similarity: log-scale weighted euclidean distance.

Log10 because mineral ranges span orders of magnitude (Na goes 0-1200 mg/L,
Mg 0-130): a 100 mg gap means nothing in TDS and everything in sodium.
TDS weighs double — it is the one-number summary of a water's character.
"""

import math
from typing import Optional

from packages.be_water.web import geo
from packages.be_water.web.domain import Water

_VECTOR_FIELDS = [
    ("tds", 2.0),
    ("bicarbonates", 1.0),
    ("chlorides", 1.0),
    ("sulfates", 1.0),
    ("calcium", 1.0),
    ("magnesium", 1.0),
    ("sodium", 1.5),
]

# Below this many shared fields two waters are simply not comparable.
# Guards against sparse labels (Lanjarón prints 4 values) clustering with
# other sparse labels just because their missing fields "match" as zeros.
MIN_SHARED_FIELDS = 3


def distance(a: dict, b: dict) -> float:
    """Weighted log-scale distance over the fields BOTH waters declare.

    Normalized by the number of shared fields so pairs with different
    coverage stay comparable; `inf` when the overlap is too small to
    mean anything.
    """
    diffs = []
    for field, weight in _VECTOR_FIELDS:
        va, vb = a.get(field), b.get(field)
        if va is None or vb is None:
            continue
        diffs.append(((math.log10(va + 1) - math.log10(vb + 1)) * weight) ** 2)
    if len(diffs) < MIN_SHARED_FIELDS:
        return math.inf
    return math.sqrt(sum(diffs) / len(diffs))


def similar_waters(
    target: Water, catalog: list[Water], top_n: int = 3
) -> list[tuple[Water, float]]:
    """Closest waters to `target` in the catalog (excluding itself)."""
    scored = [
        (w, distance(target.minerals, w.minerals)) for w in catalog if w.id != target.id
    ]
    scored = [(w, d) for w, d in scored if math.isfinite(d)]
    scored.sort(key=lambda t: t[1])
    return scored[:top_n]


def favorites_centroid(favorites: list[Water]) -> Optional[dict]:
    """Mean mineral profile of the user's favorites (linear-space mean)."""
    if not favorites:
        return None
    fields = [f for f, _ in _VECTOR_FIELDS]
    centroid: dict = {}
    for f in fields:
        values = [w.minerals.get(f) for w in favorites]
        values = [v for v in values if v is not None]
        centroid[f] = sum(values) / len(values) if values else None
    return centroid


def favorites_profile(favorites: list[Water]) -> Optional[dict]:
    """Median mineral profile of the user's favorites.

    The mean is what the recommender needs — a centre of mass to measure
    distance from. It is the wrong thing to *describe* a taste with: one
    unusual favorite drags it. A single strong water nearly tripled the
    sulfate mean of a seven-water set (22 → 60 mg/L) and became the first
    trait the profile page announced, describing that one bottle rather than
    the six others.

    The median says what a typical favorite looks like, which is the claim
    the page is actually making.
    """
    if not favorites:
        return None
    profile: dict = {}
    for field, _ in _VECTOR_FIELDS:
        values = sorted(
            w.minerals[field] for w in favorites if w.minerals.get(field) is not None
        )
        profile[field] = values[len(values) // 2] if values else None
    return profile


def mineralization_spread(favorites: list[Water]) -> Optional[tuple]:
    """`(min, max)` dry residue across the favorites, or None.

    The headline class comes from the mean and cannot move: with six waters
    near 250 mg/L, even a seventh at 1400 leaves the average under the 500
    boundary. True of the average, misleading about the collection — so the
    page shows the range beside it.
    """
    values = [w.minerals["tds"] for w in favorites if w.minerals.get("tds") is not None]
    return (min(values), max(values)) if values else None


_TRAIT_LABELS = {
    "bicarbonates": ("rica en bicarbonatos", "baja en bicarbonatos"),
    "chlorides": ("con carácter salino", "casi sin cloruros"),
    "sulfates": ("rica en sulfatos", "baja en sulfatos"),
    "calcium": ("rica en calcio", "baja en calcio"),
    "magnesium": ("rica en magnesio", "baja en magnesio"),
    "sodium": ("alta en sodio", "muy baja en sodio"),
}


def profile_traits(centroid: dict, catalog: list[Water], top_n: int = 3) -> list[str]:
    """Describe what stands out in the user's taste vs the catalog.

    Compares the favorites centroid against the catalog median per mineral
    (log-scale, declared values only) and words the strongest deviations.
    TDS is excluded — the mineralization class already headlines it.
    """
    deviations = []
    for field, labels in _TRAIT_LABELS.items():
        value = centroid.get(field)
        if value is None:
            continue
        observed = sorted(
            w.minerals[field] for w in catalog if w.minerals.get(field) is not None
        )
        if len(observed) < 5:
            continue
        median = observed[len(observed) // 2]
        ratio = math.log10(value + 1) - math.log10(median + 1)
        if abs(ratio) < 0.12:  # ~±30% — not distinctive enough to mention
            continue
        deviations.append((abs(ratio), labels[0] if ratio > 0 else labels[1]))
    deviations.sort(reverse=True)
    return [label for _, label in deviations[:top_n]]


def waters_in_place(catalog: list[Water], place: str) -> list[Water]:
    """Every catalog water from `place`, matched against province or community.

    A pure filter: no favourites, no scoring, no cap. What a region holds does
    not depend on who is asking — identity reorders this list, it never
    changes it.

    An empty `place` yields nothing. It would otherwise match every water
    whose community is blank, since `place_key("")` equals a missing field.
    """
    key = geo.place_key(place)
    if not key:
        return []
    return [
        w
        for w in catalog
        if key in (geo.place_key(w.province), geo.place_key(w.community))
    ]


def waters_near_place(catalog: list[Water], place: str) -> list[Water]:
    """Waters from the provinces bordering `place`, excluding the place's own.

    "What else is around" — so unlike `waters_in_place`, a water of the
    searched region never appears here, and the caller drops the favourites
    on top of that.
    """
    neighbor_keys = {geo.place_key(n) for n in geo.adjacent_places(place)}
    if not neighbor_keys:
        return []
    own = {w.id for w in waters_in_place(catalog, place)}
    return [
        w
        for w in catalog
        if w.id not in own and geo.place_key(w.province) in neighbor_keys
    ]


def by_mineralization(waters: list[Water]) -> list[Water]:
    """Neutral order: ascending dry residue, undeclared TDS last, name to break
    ties so the page does not reshuffle between requests.

    `None` and a float do not compare, so "last" has to be its own leading
    term rather than a sentinel value.
    """
    return sorted(waters, key=lambda w: (w.tds is None, w.tds or 0, w.name))


def rank_by_centroid(waters: list[Water], centroid: dict) -> list[Water]:
    """`waters` closest-first to a favourites centroid.

    Waters too sparse to compare (`inf` distance) are appended in neutral
    order rather than dropped: this ranks a list that claims to be a whole
    region, and a region's water disappearing from it is a worse answer than
    an unranked one.
    """
    scored = [(w, distance(centroid, w.minerals)) for w in waters]
    comparable = sorted((t for t in scored if math.isfinite(t[1])), key=lambda t: t[1])
    incomparable = by_mineralization([w for w, d in scored if not math.isfinite(d)])
    return [w for w, _ in comparable] + incomparable
