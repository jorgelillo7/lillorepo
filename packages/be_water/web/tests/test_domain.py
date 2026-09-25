"""Tests for the Water domain model — provenance fields."""

from packages.be_water.web.domain import Water


def _water(**kw) -> Water:
    base = dict(id="w", name="W", brand="", spring="", province="", community="")
    base.update(kw)
    return Water(**base)


def test_sources_round_trip():
    water = _water(
        minerals={"tds": 261, "calcium": 59.5},
        verified_fields=["calcium"],
        sources={"tds": "manual", "province": "aesan"},
    )
    restored = Water.from_firestore(water.id, water.to_firestore())
    assert restored.sources == {"tds": "manual", "province": "aesan"}
    assert restored.verified_fields == ["calcium"]


def test_from_firestore_defaults_sources_to_empty():
    assert Water.from_firestore("w", {"name": "W"}).sources == {}


def test_source_of_prefers_label_from_verified_fields():
    water = _water(
        verified_fields=["calcium"],
        sources={"calcium": "manual", "tds": "manual"},
    )
    # verified_fields wins even if sources also lists the field.
    assert water.source_of("calcium") == "label"
    assert water.source_of("tds") == "manual"
    assert water.source_of("sodium") is None


# --- a water knows whether Spanish geography applies to it -----------------


def test_a_water_is_spanish_by_default():
    """Every ficha written before `country` existed, and every Spanish one."""
    assert Water(
        id="x", name="X", brand="X", spring="", province="", community=""
    ).is_spanish


def test_a_foreign_water_is_not_spanish():
    water = Water(
        id="fontebil",
        name="FONTÉBIL",
        brand="FONTÉBIL",
        spring="Fontébil 1",
        province="Fafe",
        community="",
        country="PT",
    )
    assert not water.is_spanish
    assert water.country_name == "Portugal"


def test_an_unknown_country_code_still_renders_something():
    """A code with no name in the table must not blank the origin panel."""
    water = Water(
        id="x", name="X", brand="X", spring="", province="", community="", country="ZZ"
    )
    assert water.country_name == "ZZ"


# --- the identity the label prints and the model never kept ----------------


def test_a_water_carries_its_registry_number_and_bottler():
    water = Water(
        id="x",
        name="X",
        brand="X",
        spring="Encinas",
        province="Badajoz",
        community="Extremadura",
        registry_id="27.02231/BA",
        bottler="SONEPA",
    )
    assert water.to_firestore()["registry_id"] == "27.02231/BA"
    assert water.to_firestore()["bottler"] == "SONEPA"


def test_both_default_to_empty_for_every_existing_ficha():
    water = Water(id="x", name="X", brand="X", spring="", province="", community="")
    assert water.registry_id == ""
    assert water.bottler == ""
    assert Water.from_firestore("x", {"name": "X"}).registry_id == ""
