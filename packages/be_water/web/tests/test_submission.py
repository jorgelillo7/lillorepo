"""Unit tests for `submission.py` — the add-water logic extracted from the
route so the slug/duplicate/merge/verification rules are testable without a
request. Route wiring (CSRF, limits, form re-render) stays in test_routes.py.
"""

from packages.be_water.web import submission
from packages.be_water.web.domain import Water


def _water(**kw) -> Water:
    base = dict(id="w", name="W", brand="", spring="", province="", community="")
    base.update(kw)
    return Water(**base)


# --- slug / duplicate guards ------------------------------------------------


def test_slugify_folds_accents():
    assert submission.slugify("Lanjarón") == "lanjaron"
    assert submission.slugify("Solán de Cabras!") == "solan-de-cabras"


def test_springs_differ_only_for_genuinely_different_sources():
    assert submission.springs_differ("Sacalm", "Sigüenza") is True
    assert (
        submission.springs_differ("Fuente Alta", "Fuente Alta Norte") is False
    )  # subset
    assert submission.springs_differ("", "Bezoya") is False  # one side blank


def test_similar_water_matches_on_token_subset():
    catalog = [_water(id="naturis-lidl", name="Naturis (Lidl)", brand="Naturis")]
    assert submission.similar_water("Naturis", catalog).id == "naturis-lidl"
    assert submission.similar_water("Bezoya", catalog) is None


def test_disambiguated_id_appends_new_spring_tokens_only():
    assert (
        submission.disambiguated_id("font-vella", "Sigüenza") == "font-vella-siguenza"
    )
    # A spring already reflected in the id adds nothing.
    assert submission.disambiguated_id("fuente-liviana", "Liviana") == "fuente-liviana"


# --- form parsing -----------------------------------------------------------


def test_parse_minerals_normalises_comma_and_guards_range():
    form = {"tds": "261,5", "calcium": "60", "sodium": "-3", "ph": "abc"}
    minerals = submission.parse_minerals(form)
    assert minerals["tds"] == 261.5  # European decimal comma → dot
    assert minerals["calcium"] == 60
    assert "sodium" not in minerals  # negative dropped
    assert "ph" not in minerals  # unparseable dropped


def test_verified_fields_only_keeps_declared_minerals():
    minerals = {"tds": 100, "calcium": 50}
    assert submission.verified_fields_from_ocr("tds,sodium,calcium", minerals) == [
        "calcium",
        "tds",
    ]


def test_build_water_defaults_brand_to_name():
    water = submission.build_water(
        {"brand": ""},
        water_id="w",
        name="Bezoya",
        minerals={"tds": 27},
        verified_fields=[],
        photo_url=None,
        label_photo_url=None,
        added_by="jorge",
    )
    assert water.brand == "Bezoya"
    assert water.added_by == "jorge"
    assert water.added_at  # timestamp set


# --- merge semantics --------------------------------------------------------


def test_apply_existing_form_wins_but_preserves_uncarried_fields():
    existing = _water(
        minerals={"tds": 99, "calcium": 50},
        photo_url="gs://x/photo.jpg",
        added_by="maria",
        added_at="2026-01-01T00:00:00+00:00",
        brand="OldBrand",
    )
    water = submission.build_water(
        {"brand": ""},  # no brand on the form
        water_id="w",
        name="W",
        minerals={"tds": 27},  # form's tds wins
        verified_fields=[],
        photo_url=None,  # no new photo
        label_photo_url=None,
        added_by="jorge",
    )
    submission.apply_existing(water, existing, merge_into=False, form_has_brand=False)
    assert water.minerals == {"calcium": 50, "tds": 27}  # merged, form's tds wins
    assert water.photo_url == "gs://x/photo.jpg"  # survived
    assert water.brand == "OldBrand"  # no form brand → existing kept
    assert water.added_by == "maria"  # real author preserved
    assert water.added_at == "2026-01-01T00:00:00+00:00"


def test_apply_existing_adopts_seed_water_for_the_new_contributor():
    existing = _water(added_by="seed", added_at=None)
    water = submission.build_water(
        {},
        water_id="w",
        name="W",
        minerals={},
        verified_fields=[],
        photo_url=None,
        label_photo_url=None,
        added_by="jorge",
    )
    submission.apply_existing(water, existing, merge_into=False, form_has_brand=False)
    assert water.added_by == "jorge"  # seed is adopted, not preserved


def test_apply_existing_merge_into_keeps_canonical_name():
    existing = _water(name="Font Vella", retailer="Danone")
    water = submission.build_water(
        {},
        water_id="fv",
        name="fontvella typo",
        minerals={},
        verified_fields=[],
        photo_url=None,
        label_photo_url=None,
        added_by="jorge",
    )
    submission.apply_existing(water, existing, merge_into=True, form_has_brand=False)
    assert water.name == "Font Vella"
    assert water.retailer == "Danone"


# --- provenance + auto-verification -----------------------------------------


def test_finalize_auto_verifies_when_label_backs_every_mineral():
    water = _water(
        minerals={"tds": 100},
        verified_fields=["tds"],
        label_photo_url="gs://x/label.jpg",
    )
    submission.finalize_provenance(water, existing=None)
    assert water.verified is True


def test_finalize_does_not_verify_without_full_label_backing():
    water = _water(
        minerals={"tds": 100, "calcium": 50},
        verified_fields=["tds"],  # calcium not label-backed
        label_photo_url="gs://x/label.jpg",
    )
    submission.finalize_provenance(water, existing=None)
    assert water.verified is False
    assert water.sources["calcium"] == "manual"
