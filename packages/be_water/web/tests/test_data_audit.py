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
