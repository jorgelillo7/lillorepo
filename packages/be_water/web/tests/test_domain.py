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
        sources={"tds": "manufacturer", "province": "aesan"},
    )
    restored = Water.from_firestore(water.id, water.to_firestore())
    assert restored.sources == {"tds": "manufacturer", "province": "aesan"}
    assert restored.verified_fields == ["calcium"]


def test_from_firestore_defaults_sources_to_empty():
    assert Water.from_firestore("w", {"name": "W"}).sources == {}


def test_source_of_prefers_label_from_verified_fields():
    water = _water(
        verified_fields=["calcium"],
        sources={"calcium": "manual", "tds": "manufacturer"},
    )
    # verified_fields wins even if sources also lists the field.
    assert water.source_of("calcium") == "label"
    assert water.source_of("tds") == "manufacturer"
    assert water.source_of("sodium") is None
