"""Tests for the curation engine — verification sign-off."""

from unittest.mock import patch

import pytest

from packages.be_water.web import data_audit
from packages.be_water.web.domain import Water

_MOD = "packages.be_water.web.data_audit"


def _water(**kw) -> Water:
    base = dict(id="w", name="W", brand="", spring="", province="", community="")
    base.update(kw)
    return Water(**base)


def test_verifiable_needs_label_photo_and_a_label_field():
    assert data_audit.verifiable(
        _water(label_photo_url="u", verified_fields=["calcium"])
    )
    # Missing either requirement → not eligible.
    assert not data_audit.verifiable(_water(verified_fields=["calcium"]))
    assert not data_audit.verifiable(_water(label_photo_url="u"))
    # Already verified → nothing to sign off.
    assert not data_audit.verifiable(
        _water(label_photo_url="u", verified_fields=["calcium"], verified=True)
    )


def test_mark_verified_freezes_and_saves():
    water = _water(label_photo_url="u", verified_fields=["calcium"])
    with patch(f"{_MOD}.repository.save_water") as save:
        data_audit.mark_verified(water)
    assert water.verified is True
    save.assert_called_once_with(water)


def test_mark_verified_refuses_without_proof():
    with patch(f"{_MOD}.repository.save_water") as save:
        with pytest.raises(ValueError):
            data_audit.mark_verified(_water(verified_fields=["calcium"]))  # no photo
    save.assert_not_called()


# --- duplicates -------------------------------------------------------------


def test_find_duplicates_groups_same_name_compatible_spring():
    catalog = [
        _water(id="font-vella", name="Font Vella", spring="Sacalm"),
        _water(id="font-vella-2", name="Font Vella", spring=""),  # spring unknown
        _water(id="bezoya", name="Bezoya", spring="Bezoya"),
    ]
    groups = data_audit.find_duplicates(catalog)
    assert len(groups) == 1
    assert {w.id for w in groups[0]} == {"font-vella", "font-vella-2"}


def test_find_duplicates_leaves_multi_spring_brands_alone():
    catalog = [
        _water(id="fv-sacalm", name="Font Vella", spring="Sacalm"),
        _water(id="fv-siguenza", name="Font Vella", spring="Sigüenza"),
    ]
    assert data_audit.find_duplicates(catalog) == []  # genuinely different springs


# --- suspicious -------------------------------------------------------------


def test_suspicious_flags_ph_and_ion_incoherence():
    bad_ph = _water(minerals={"ph": 12})
    assert any("pH" in r for r in data_audit.suspicious_reasons(bad_ph))

    incoherent = _water(minerals={"tds": 2000, "calcium": 10, "sodium": 5})
    assert any("residuo seco" in r for r in data_audit.suspicious_reasons(incoherent))


def test_suspicious_clean_water_has_no_reasons():
    clean = _water(minerals={"tds": 250, "bicarbonates": 200, "calcium": 60, "ph": 7.4})
    assert data_audit.suspicious_reasons(clean) == []


# --- repairs ----------------------------------------------------------------


def test_set_source_moves_field_in_and_out_of_verified():
    water = _water(verified_fields=["tds"], sources={})
    with patch(f"{_MOD}.repository.save_water"):
        data_audit.set_source(water, "tds", "manufacturer")
    assert water.verified_fields == []
    assert water.sources["tds"] == "manufacturer"
    with patch(f"{_MOD}.repository.save_water"):
        data_audit.set_source(water, "tds", "label")
    assert water.verified_fields == ["tds"]
    assert "tds" not in water.sources


def test_merge_waters_folds_and_deletes_drop():
    keep = _water(id="keep", minerals={"tds": 100}, verified_fields=["tds"])
    drop = _water(
        id="drop",
        minerals={"tds": 999, "calcium": 50},  # tds conflict → keep wins
        label_photo_url="lbl",
        sources={"calcium": "manufacturer"},
    )
    with patch(f"{_MOD}.repository.save_water") as save, patch(
        f"{_MOD}.repository.delete_water"
    ) as delete:
        data_audit.merge_waters(keep, drop)
    assert keep.minerals == {"tds": 100, "calcium": 50}
    assert keep.label_photo_url == "lbl"  # filled from drop
    assert keep.sources["calcium"] == "manufacturer"
    save.assert_called_once_with(keep)
    delete.assert_called_once_with("drop")


# --- dataset drift ----------------------------------------------------------

_DATASET = [{"id": "w", "minerals": {"tds": 490, "calcium": 120.0, "sodium": 5.0}}]


def test_dataset_drift_reports_where_the_repo_disagrees_with_the_catalog():
    live = _water(minerals={"tds": 649, "calcium": 120.0}, verified_fields=["tds"])
    with patch(f"{_MOD}.SEED_WATERS", _DATASET):
        ((water, differences),) = data_audit.dataset_drift([live])
    assert water is live
    # Only the moved field, tagged so a stale dataset is told from a bad value;
    # `sodium` is absent from the ficha, so there is nothing to compare.
    assert differences == ["Residuo seco: dataset 490 vs ficha 649 [etiqueta]"]


def test_dataset_drift_is_silent_when_the_dataset_agrees():
    live = _water(minerals={"tds": 490, "calcium": 120.0})
    with patch(f"{_MOD}.SEED_WATERS", _DATASET):
        assert data_audit.dataset_drift([live]) == []


def test_dataset_drift_ignores_waters_the_dataset_never_seeded():
    live = _water(id="user-added", minerals={"tds": 10})
    with patch(f"{_MOD}.SEED_WATERS", _DATASET):
        assert data_audit.dataset_drift([live]) == []
