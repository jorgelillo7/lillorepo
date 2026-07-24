"""Tests for provenance.derive_sources."""

from unittest.mock import patch

from packages.be_water.web import provenance
from packages.be_water.web.domain import Water

_MOD = "packages.be_water.web.provenance"


def _water(**kw) -> Water:
    base = dict(id="w", name="W", brand="", spring="", province="", community="")
    base.update(kw)
    return Water(**base)


def test_seed_matching_values_are_manufacturer_label_fields_excluded():
    water = _water(
        id="solan",
        minerals={"tds": 261, "calcium": 59.5, "sodium": 5.2},
        verified_fields=["calcium"],
    )
    seed = {"solan": {"tds": 261, "calcium": 59.5, "sodium": 5.2}}
    with patch.dict(f"{_MOD}._SEED_MINERALS", seed, clear=True), patch(
        f"{_MOD}.aesan.registry_matches", return_value=[]
    ):
        sources = provenance.derive_sources(water)
    # calcium is label (in verified_fields) → not stored; the rest manufacturer.
    assert sources == {"tds": "manufacturer", "sodium": "manufacturer"}


def test_value_changed_from_seed_is_manual():
    water = _water(id="solan", minerals={"tds": 999})  # seed had 261
    seed = {"solan": {"tds": 261}}
    with patch.dict(f"{_MOD}._SEED_MINERALS", seed, clear=True), patch(
        f"{_MOD}.aesan.registry_matches", return_value=[]
    ):
        assert provenance.derive_sources(water) == {"tds": "manual"}


def test_value_absent_from_seed_is_manual():
    water = _water(id="newbie", minerals={"tds": 100})
    with patch.dict(f"{_MOD}._SEED_MINERALS", {}, clear=True), patch(
        f"{_MOD}.aesan.registry_matches", return_value=[]
    ):
        assert provenance.derive_sources(water) == {"tds": "manual"}


def test_existing_source_is_kept():
    water = _water(id="solan", minerals={"tds": 261}, sources={"tds": "manual"})
    seed = {"solan": {"tds": 261}}
    with patch.dict(f"{_MOD}._SEED_MINERALS", seed, clear=True), patch(
        f"{_MOD}.aesan.registry_matches", return_value=[]
    ):
        assert provenance.derive_sources(water)["tds"] == "manual"


def test_province_and_community_from_aesan_registry():
    water = _water(name="Solán", province="Cuenca", community="Castilla-La Mancha")
    matches = [{"province": "Cuenca"}]
    with patch(f"{_MOD}.aesan.registry_matches", return_value=matches), patch(
        f"{_MOD}.geo.community_of", return_value="Castilla-La Mancha"
    ):
        sources = provenance.derive_sources(water)
    assert sources["province"] == "aesan"
    assert sources["community"] == "aesan"


def test_no_aesan_source_when_registry_disagrees():
    water = _water(name="X", province="Cuenca")
    mismatch = [{"province": "Segovia"}]
    with patch(f"{_MOD}.aesan.registry_matches", return_value=mismatch):
        assert "province" not in provenance.derive_sources(water)
