"""The decision `purge_manufacturer_sources` makes for each 'fabricante' value."""

from packages.be_water.scripts.purge_manufacturer_sources import plan

_LABEL = "https://storage.googleapis.com/be-water-photos/originals/x__2024.jpg"


def test_a_value_no_label_backs_is_removed_with_its_source():
    ficha = {
        "minerals": {"tds": 179.0, "silica": 24.0},
        "verified_fields": ["tds"],
        "sources": {"silica": "manufacturer", "province": "aesan"},
        "label_photo_url": _LABEL,
    }
    new, verified, removed = plan(ficha, backing=None)
    assert removed == ["silica"] and verified == []
    assert new["minerals"] == {"tds": 179.0}
    assert new["sources"] == {"province": "aesan"}


def test_an_entry_value_its_ficha_read_off_the_same_label_becomes_verified():
    """Same photo, same value, verified on the ficha: real data, wrong mark."""
    ficha = {
        "minerals": {"tds": 235},
        "verified_fields": ["tds"],
        "label_photo_url": _LABEL,
    }
    entry = {
        "minerals": {"tds": 235},
        "verified_fields": [],
        "sources": {"tds": "manufacturer"},
        "label_photo_url": _LABEL,
    }
    new, verified, removed = plan(entry, backing=ficha)
    assert verified == ["tds"] and removed == []
    assert new["verified_fields"] == ["tds"] and new["minerals"] == {"tds": 235}
    assert new["sources"] == {}


def test_a_different_value_or_photo_is_not_backing():
    ficha = {
        "minerals": {"tds": 240},
        "verified_fields": ["tds"],
        "label_photo_url": _LABEL,
    }
    entry = {
        "minerals": {"tds": 235},
        "sources": {"tds": "manufacturer"},
        "label_photo_url": _LABEL,
    }
    assert plan(entry, backing=ficha)[2] == ["tds"]
    ficha["minerals"]["tds"] = 235
    ficha["label_photo_url"] = _LABEL + "?other"
    assert plan(entry, backing=ficha)[2] == ["tds"]
