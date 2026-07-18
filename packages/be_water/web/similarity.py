"""Mineral-profile similarity: log-scale weighted euclidean distance.

Log10 because mineral ranges span orders of magnitude (Na goes 0-1200 mg/L,
Mg 0-130): a 100 mg gap means nothing in TDS and everything in sodium.
TDS weighs double — it is the one-number summary of a water's character.
"""

import math
from typing import Optional

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


def recommend(
    favorites: list[Water],
    catalog: list[Water],
    place: str,
    top_n: int = 5,
) -> list[tuple[Water, float]]:
    """Waters from `place` (province or community), closest to the user's
    favorites centroid. Excludes the favorites themselves."""
    centroid = favorites_centroid(favorites)
    if centroid is None:
        return []
    fav_ids = {w.id for w in favorites}
    place_lower = place.strip().lower()
    candidates = [
        w
        for w in catalog
        if w.id not in fav_ids
        and place_lower in (w.province.lower(), w.community.lower())
    ]
    scored = [(w, distance(centroid, w.minerals)) for w in candidates]
    scored = [(w, d) for w, d in scored if math.isfinite(d)]
    scored.sort(key=lambda t: t[1])
    return scored[:top_n]
