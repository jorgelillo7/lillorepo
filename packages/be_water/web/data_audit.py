"""Curation engine for the be_water catalog.

Phase 3 covers verification sign-off; phase 4 adds duplicate/anomaly
detection. Reused by the CLI (scripts/audit_data.py) and the future admin
page, same pattern as photo_audit.
"""

from packages.be_water.web import repository
from packages.be_water.web.domain import Water


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
