"""Tests for provenance: where each field of a ficha came from."""

from unittest.mock import patch

from packages.be_water.web import provenance
from packages.be_water.web.domain import Water

_MOD = "packages.be_water.web.provenance"


def _water(**kw) -> Water:
    base = dict(id="w", name="W", brand="", spring="", province="", community="")
    base.update(kw)
    return Water(**base)


# --- derive_sources ---------------------------------------------------------


def test_a_mineral_with_no_recorded_source_stays_unknown():
    """Nothing here can know who wrote a number nobody recorded, so it says
    nothing — naming a source would be inventing one."""
    water = _water(minerals={"tds": 261, "calcium": 59.5}, verified_fields=["calcium"])
    with patch(f"{_MOD}.aesan.registry_matches", return_value=[]):
        assert provenance.derive_sources(water) == {}


def test_existing_source_is_kept():
    water = _water(minerals={"tds": 261}, sources={"tds": "manual"})
    with patch(f"{_MOD}.aesan.registry_matches", return_value=[]):
        assert provenance.derive_sources(water) == {"tds": "manual"}


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


# --- sources_on_save --------------------------------------------------------


def test_what_the_contributor_submitted_is_manual_labels_implied():
    result = provenance.sources_on_save(
        minerals={"tds": 100, "calcium": 50},
        verified_fields=["calcium"],  # label → not stored
        existing_sources={},
        submitted={"tds", "calcium"},
    )
    assert result == {"tds": "manual"}


def test_a_value_merged_from_the_ficha_is_not_credited_to_the_contributor():
    """Lunares, in production. Its label declares eight minerals; the ficha
    held ten, `apply_existing` merged the two the label never printed through,
    and the ficha then told the contributor they had typed them by hand. A
    value the contributor did not submit keeps the source it had — here none."""
    result = provenance.sources_on_save(
        minerals={"tds": 950, "ph": 7.2, "calcium": 94.5},
        verified_fields=["calcium"],
        existing_sources={},
        submitted={"calcium"},
    )
    assert result == {}


def test_a_merged_value_keeps_the_source_it_had():
    result = provenance.sources_on_save(
        minerals={"tds": 100, "sodium": 5},
        verified_fields=[],
        existing_sources={"tds": "manual", "province": "aesan"},
        submitted={"sodium"},
    )
    assert result == {"tds": "manual", "province": "aesan", "sodium": "manual"}


def test_resubmitting_a_value_makes_it_the_contributor_s():
    result = provenance.sources_on_save(
        minerals={"tds": 999},
        verified_fields=[],
        existing_sources={"tds": "aesan"},
        submitted={"tds"},
    )
    assert result == {"tds": "manual"}


def test_sources_on_save_drops_vanished_and_label_fields():
    result = provenance.sources_on_save(
        minerals={"tds": 100},
        verified_fields=["tds"],  # tds is now label-backed
        existing_sources={"tds": "manual", "calcium": "manual"},
        submitted={"tds"},
    )
    # tds became label → dropped; calcium no longer a mineral → dropped.
    assert result == {}
