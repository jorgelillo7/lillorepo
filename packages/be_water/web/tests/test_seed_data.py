"""Integrity of the in-repo dataset.

`seed_data.py` is what recreates the catalog on an empty Firestore and what
`catalog_sync` reconciles against every month, so a claim it makes wrongly is
one the live catalog eventually inherits. These are the invariants a human
editing it by hand can break without any test noticing.
"""

from packages.be_water.web.domain import MINERAL_FIELDS
from packages.be_water.web.seed_data import SEED_WATERS


def test_ids_are_unique():
    ids = [raw["id"] for raw in SEED_WATERS]
    assert len(ids) == len(set(ids))


def test_declared_mineral_fields_are_real():
    """A typo'd key is stored, ignored by every reader, and invisible."""
    for raw in SEED_WATERS:
        for field in raw.get("minerals", {}):
            assert field in MINERAL_FIELDS, f"{raw['id']}: unknown mineral {field}"


def test_verified_fields_name_minerals_the_entry_actually_declares():
    """`verified_fields` says "this value is printed on a photographed label".
    Naming a field the entry does not carry claims proof for a number that is
    not there — and `catalog_sync` copies the list into Firestore, where it
    then protects nothing."""
    for raw in SEED_WATERS:
        minerals = raw.get("minerals", {})
        for field in raw.get("verified_fields", []):
            assert field in MINERAL_FIELDS, f"{raw['id']}: unknown field {field}"
            assert field in minerals, f"{raw['id']}: {field} verified but not declared"


def test_a_verified_water_carries_the_photo_that_verifies_it():
    """`verified` is the frozen state: `catalog_sync` will not touch the ficha
    again. Freezing one with no photo at all freezes an unprovable claim.

    The stronger rule — a verified water names the fields its label declares —
    is not asserted here yet: `aquadeus` is frozen with a front-of-bottle shot
    and no label-confirmed value, which is a data decision for the owner, not
    something a test may quietly define away."""
    for raw in SEED_WATERS:
        if raw.get("verified"):
            assert raw.get("label_photo_url"), f"{raw['id']}: verified, no label photo"
