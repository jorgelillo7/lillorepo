"""Derive per-field provenance (``Water.sources``) from what we know.

Label-confirmed fields live in ``verified_fields`` (they drive the ✓); this
records the source of everything else so the UI can name it — "AESAN"
(identity cross-checked against the official registry) or "a mano" (the
contributor submitted it). A field nobody recorded a source for stays
unknown: naming one would be inventing it.

Pure functions: the save path and the backfill script both call them.
"""

from packages.be_water.web import aesan, geo
from packages.be_water.web.domain import SOURCE_AESAN, SOURCE_MANUAL, Water

# Non-mineral fields whose provenance is worth keeping in `sources`.
_IDENTITY_KEYS = ("province", "community", "spring")


def sources_on_save(
    minerals: dict,
    verified_fields: list,
    existing_sources: dict,
    submitted: set,
) -> dict:
    """Provenance after a form save.

    Label fields are implied by `verified_fields`, so they are dropped here.
    A mineral the contributor `submitted` that was not read off the label is
    `manual`. A mineral merged through from the ficha keeps the source it
    had, or none: Lunares' label declares eight minerals, the ficha held ten,
    and crediting the two merged-through values to whoever photographed the
    bottle made the ficha assert they had typed them.
    """
    verified = set(verified_fields)
    keep = set(minerals) | set(_IDENTITY_KEYS)
    result = {
        field_name: source
        for field_name, source in existing_sources.items()
        if field_name in keep and field_name not in verified
    }
    for field_name in minerals:
        if field_name in submitted and field_name not in verified:
            result[field_name] = SOURCE_MANUAL
    return result


def derive_sources(water: Water) -> dict:
    """Provenance map for a water: the sources it already records, plus the
    AESAN identity sources the registry can vouch for. Minerals are never
    filled in — who wrote an unrecorded number cannot be known after the
    fact. Any source already on the water is kept, so the backfill is
    idempotent."""
    sources = dict(water.sources)

    # Identity: province/community are AESAN-sourced when the registry lists
    # this name under a single province that matches the ficha.
    matches = aesan.registry_matches(water.name)
    provinces = {m["province"] for m in matches}
    if len(provinces) == 1 and water.province and water.province in provinces:
        sources.setdefault("province", SOURCE_AESAN)
        if water.community and water.community == geo.community_of(water.province):
            sources.setdefault("community", SOURCE_AESAN)
    return sources
