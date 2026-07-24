"""Curation engine for the be_water catalog.

Phase 3 covers verification sign-off; phase 4 adds duplicate/anomaly
detection. Reused by the CLI (scripts/audit_data.py) and the future admin
page, same pattern as photo_audit.
"""

import re

from unidecode import unidecode

from packages.be_water.web import repository
from packages.be_water.web.domain import MINERAL_FIELDS, SOURCE_LABEL, Water

_SLUG = re.compile(r"[^a-z0-9]+")
# Major dissolved ions whose sum should track the dry residue (tds).
_IONS = [f for f in MINERAL_FIELDS if f not in ("tds", "ph")]


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
    their provenance (they still render as 'fabricante' / 'a mano'); the model
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
    if tds and ion_sum and (tds > ion_sum * 2 or tds < ion_sum * 0.2):
        reasons.append(
            f"residuo seco {tds} incoherente con la suma de iones {round(ion_sum)}"
        )
    return reasons


def find_suspicious(catalog: list[Water]) -> list[tuple]:
    """(water, reasons) for every ficha with at least one data-quality flag."""
    return [(w, r) for w in catalog if (r := suspicious_reasons(w))]


# --- Repairs ----------------------------------------------------------------


def merge_waters(keep: Water, drop: Water) -> None:
    """Fold `drop` into `keep` (keep wins on conflicts) and delete the drop
    doc. Drop's bucket objects are left in place — keep may now point at
    them."""
    keep.minerals = {**drop.minerals, **keep.minerals}
    keep.sources = {**drop.sources, **keep.sources}
    keep.verified_fields = sorted(set(keep.verified_fields) | set(drop.verified_fields))
    keep.photo_url = keep.photo_url or drop.photo_url
    keep.label_photo_url = keep.label_photo_url or drop.label_photo_url
    keep.mentions = keep.mentions or drop.mentions
    keep.spring = keep.spring or drop.spring
    keep.province = keep.province or drop.province
    keep.community = keep.community or drop.community
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
