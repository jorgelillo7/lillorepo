"""Derive per-field provenance (``Water.sources``) from what we know.

Label-confirmed fields live in ``verified_fields`` (they drive the ✓); this
fills the source of everything else so the UI can name it — "fabricante"
(seed came from manufacturer sites), "AESAN" (identity cross-checked against
the official registry) or "a mano" (a contributor typed it).

Pure functions: the backfill script and the future curation engine both call
``derive_sources``.
"""

from packages.be_water.web import aesan, geo
from packages.be_water.web.domain import (
    MINERAL_FIELDS,
    SOURCE_AESAN,
    SOURCE_MANUAL,
    SOURCE_MANUFACTURER,
    Water,
)
from packages.be_water.web.seed_data import SEED_WATERS

# The seed values are manufacturer-site / label transcriptions (see
# seed_data.py). A non-label value that still matches its seed is manufacturer
# data; once a contributor changed it — or added a value the seed never had —
# it is hand-entered. Using added_by would misfire: seed waters adopted by a
# contributor keep their seeded numbers but lose the "seed" author.
_SEED_MINERALS = {w["id"]: (w.get("minerals") or {}) for w in SEED_WATERS}


def derive_sources(water: Water) -> dict:
    """Provenance map for a water's non-label fields. Only fills gaps — any
    source already on the water is kept, so the backfill is idempotent."""
    sources = dict(water.sources)
    seed_minerals = _SEED_MINERALS.get(water.id, {})
    for field_name in MINERAL_FIELDS:
        if field_name not in water.minerals:
            continue
        if field_name in water.verified_fields:  # label — implied, not stored
            continue
        source = (
            SOURCE_MANUFACTURER
            if seed_minerals.get(field_name) == water.minerals[field_name]
            else SOURCE_MANUAL
        )
        sources.setdefault(field_name, source)

    # Identity: province/community are AESAN-sourced when the registry lists
    # this name under a single province that matches the ficha.
    matches = aesan.registry_matches(water.name)
    provinces = {m["province"] for m in matches}
    if len(provinces) == 1 and water.province and water.province in provinces:
        sources.setdefault("province", SOURCE_AESAN)
        if water.community and water.community == geo.community_of(water.province):
            sources.setdefault("community", SOURCE_AESAN)
    return sources
