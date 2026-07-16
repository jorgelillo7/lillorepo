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


def _vector(minerals: dict) -> list[float]:
    return [math.log10((minerals.get(f) or 0) + 1) * w for f, w in _VECTOR_FIELDS]


def distance(a: dict, b: dict) -> float:
    """Weighted log-scale euclidean distance between two mineral dicts."""
    va, vb = _vector(a), _vector(b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(va, vb)))


def similar_waters(
    target: Water, catalog: list[Water], top_n: int = 3
) -> list[tuple[Water, float]]:
    """Closest waters to `target` in the catalog (excluding itself)."""
    scored = [
        (w, distance(target.minerals, w.minerals)) for w in catalog if w.id != target.id
    ]
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
    scored.sort(key=lambda t: t[1])
    return scored[:top_n]
