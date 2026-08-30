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


def test_a_verified_water_names_the_fields_its_label_declares():
    """`verified` is the frozen state: `catalog_sync` will never touch the ficha
    again. Freezing one with no label photo, or with no field that photo
    confirms, freezes a claim nothing can back — which is what both `aquadeus`
    and `valtorre` were, signed off against front-of-bottle shots while every
    value on them still read "fabricante"."""
    for raw in SEED_WATERS:
        if raw.get("verified"):
            assert raw.get("label_photo_url"), f"{raw['id']}: verified, no label photo"
            assert raw.get("verified_fields"), f"{raw['id']}: verified, no fields"
