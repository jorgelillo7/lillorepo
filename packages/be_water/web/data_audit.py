"""Curation engine for the be_water catalog.

Phase 3 covers verification sign-off; phase 4 adds duplicate/anomaly
detection. Reused by the CLI (scripts/audit_data.py) and the future admin
page, same pattern as photo_audit.
"""

import re

from unidecode import unidecode

from packages.be_water.web import geo, repository
from packages.be_water.web.domain import (
    MINERAL_FIELDS,
    SOURCE_LABEL,
    Water,
)

_SLUG = re.compile(r"[^a-z0-9]+")
# Major dissolved ions whose sum should track the dry residue (tds).
_IONS = [f for f in MINERAL_FIELDS if f not in ("tds", "ph")]
# Dry residue sits below the ion sum (bicarbonates lose CO2 on drying). Across
# the 41 dataset entries the ratio spans 0.59–1.18, so these bounds clear every
# real water with margin while still catching a transposed or mis-scaled value.
_TDS_RATIO_MIN = 0.4
_TDS_RATIO_MAX = 1.5


def verifiable(water: Water) -> bool:
    """A ficha can be signed off when there's a label photo to judge against
    and at least one value already confirmed from it. The label rarely prints
    every value, so full label backing is NOT required — that is exactly the
    case the sign-off exists for."""
    return (
        not water.verified
        and bool(water.label_photo_url)
        and bool(water.verified_fields)
    )


def mark_verified(water: Water) -> None:
    """Admin sign-off: freeze the ficha as verified. Non-label values keep
    their provenance (they still render as 'a mano' or unmarked); the model
    no longer conflates a verified ficha with every field being label-backed."""
    if not water.label_photo_url or not water.verified_fields:
        raise ValueError(
            f"{water.id} is not verifiable: needs a label photo and at least "
            "one label-confirmed field"
        )
    water.verified = True
    repository.save_water(water)


# --- Duplicate detection ----------------------------------------------------


def _tokens(text: str) -> set:
    return set(_SLUG.sub(" ", unidecode(text or "").lower()).split())


def _springs_differ(a: str, b: str) -> bool:
    """True when both springs are declared and neither contains the other —
    genuinely different sources (multi-spring brand), not spelling drift."""
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta) and bool(tb) and not (ta <= tb or tb <= ta)


def find_duplicates(catalog: list[Water]) -> list[list[Water]]:
    """Groups of fichas that look like the same water under different ids:
    fuzzy name token match with compatible springs. Multi-spring brands (same
    name, genuinely different springs) are left alone — they are real
    separate waters."""
    groups = []
    grouped = set()
    for i, water in enumerate(catalog):
        if water.id in grouped:
            continue
        names = _tokens(water.name)
        group = [water]
        for other in catalog[i + 1 :]:
            if other.id in grouped:
                continue
            other_names = _tokens(other.name)
            if not (names and other_names):
                continue
            if (names <= other_names or other_names <= names) and not _springs_differ(
                water.spring, other.spring
            ):
                group.append(other)
        if len(group) > 1:
            grouped.update(g.id for g in group)
            groups.append(group)
    return groups


# --- Suspicious values ------------------------------------------------------


def suspicious_reasons(water: Water) -> list[str]:
    """Human-readable data-quality flags for one ficha (empty when clean)."""
    reasons = []
    minerals = water.minerals
    ph = minerals.get("ph")
    if ph is not None and not (3.5 <= ph <= 9.5):
        reasons.append(f"pH fuera de rango ({ph})")
    for field_name in _IONS:
        value = minerals.get(field_name)
        if value is not None and value > 3000:
            reasons.append(f"{field_name} muy alto ({value})")
    tds = minerals.get("tds")
    ion_sum = sum(minerals.get(f) or 0 for f in _IONS)
    if (
        tds
        and ion_sum
        and not (ion_sum * _TDS_RATIO_MIN <= tds <= ion_sum * _TDS_RATIO_MAX)
    ):
        reasons.append(
            f"residuo seco {tds} incoherente con la suma de iones {round(ion_sum)}"
        )
    return reasons


def find_suspicious(catalog: list[Water]) -> list[tuple]:
    """(water, reasons) for every ficha with at least one data-quality flag."""
    return [(w, r) for w in catalog if (r := suspicious_reasons(w))]


# --- Geography --------------------------------------------------------------


def geo_reasons(water: Water) -> list[str]:
    """Human-readable origin flags for one ficha (empty when clean).

    Kept apart from `suspicious_reasons`, which judges minerals: these two
    answer different questions and a ficha can fail one while passing the
    other. Both of the catalog's broken fichas did exactly that — one stored
    `province='portugal', community='portugal'`, the other no origin at all,
    and both were `verified=True` because nothing here looked at geography.

    A foreign water is **not** judged by Spanish geography. Its `province`
    holds a region that is not a province and has no community to derive, so
    checking it against `ALL_PROVINCES` would make every correct foreign ficha
    permanently suspicious. It still has to say where it is from.
    """
    reasons = []
    if not water.spring:
        reasons.append("sin manantial")
    if not water.province:
        reasons.append("sin provincia" if water.is_spanish else "sin región")
        return reasons
    if not water.is_spanish:
        return reasons
    derived = geo.community_of(water.province)
    if not derived:
        reasons.append(f"«{water.province}» no es una provincia española")
    elif not water.community:
        reasons.append(f"sin comunidad (debería ser {derived})")
    elif geo.place_key(water.community) != geo.place_key(derived):
        reasons.append(
            f"comunidad «{water.community}» no corresponde a {water.province} "
            f"(sería {derived})"
        )
    return reasons


def find_geo_gaps(catalog: list[Water]) -> list[tuple]:
    """(water, reasons) for every ficha whose origin needs a human.

    The admin page's worklist: unlike a mineral flag, none of these can be
    resolved by re-reading the label with a machine.
    """
    return [(w, r) for w in catalog if (r := geo_reasons(w))]


# --- Repairs ----------------------------------------------------------------


def merge_waters(keep: Water, drop: Water) -> None:
    """Fold `drop` into `keep` (keep wins on conflicts) and delete the drop
    doc. Drop's bucket objects are left in place — keep may now point at
    them.

    The analysis series moves across first. `delete_water` takes a water's
    entries with it, so folding only the minerals threw away the dropped
    duplicate's whole measurement history — the one part of it that is not
    reconstructable from `keep`. An entry already on `keep` for the same date
    wins, on the same rule as every other field here.
    """
    keep.minerals = {**drop.minerals, **keep.minerals}
    keep.sources = {**drop.sources, **keep.sources}
    keep.verified_fields = sorted(set(keep.verified_fields) | set(drop.verified_fields))
    keep.photo_url = keep.photo_url or drop.photo_url
    keep.label_photo_url = keep.label_photo_url or drop.label_photo_url
    keep.mentions = keep.mentions or drop.mentions
    keep.spring = keep.spring or drop.spring
    keep.province = keep.province or drop.province
    keep.community = keep.community or drop.community
    kept_dates = {e.get("analysis_date") for e in repository.list_analyses(keep.id)}
    for entry in repository.list_analyses(drop.id):
        if entry.get("analysis_date") in kept_dates:
            continue
        repository.save_analysis(keep.with_analysis(entry))
    repository.save_water(keep)
    repository.delete_water(drop.id)


def set_source(water: Water, field_name: str, source: str) -> None:
    """Change a field's provenance. 'label' moves it into verified_fields (the
    ✓); any other source moves it back out."""
    if source == SOURCE_LABEL:
        if field_name not in water.verified_fields:
            water.verified_fields = sorted(water.verified_fields + [field_name])
        water.sources.pop(field_name, None)
    else:
        water.sources[field_name] = source
        water.verified_fields = [f for f in water.verified_fields if f != field_name]
    repository.save_water(water)


def correct_field(water: Water, field_name: str, value: float, source: str) -> None:
    """Set a mineral value and its provenance, then save."""
    water.minerals[field_name] = value
    set_source(water, field_name, source)
