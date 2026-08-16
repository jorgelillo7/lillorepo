"""Structured data: what the pages claim about themselves, machine-readable."""

import json

from packages.be_water.web import seo
from packages.be_water.web.domain import Water


def _water(**kw) -> Water:
    base = dict(
        id="vichy",
        name="Vichy Catalán",
        brand="Vichy",
        spring="",
        province="Girona",
        community="Cataluña",
        minerals={"tds": 3052, "sodium": 1110, "ph": 6.8},
    )
    base.update(kw)
    return Water(**base)


HOME = "https://be-water.example"


def _page(water=None, **kw):
    water = water or _water()
    return seo.water_page(
        water,
        url=f"{HOME}/agua/{water.id}",
        home_url=HOME,
        place_url=f"{HOME}/recomendar?lugar={water.province}",
        **kw,
    )


def test_a_water_publishes_its_declared_minerals_and_nothing_else():
    product = _page()["@graph"][0]
    names = [p["name"] for p in product["additionalProperty"]]
    assert names == ["Residuo seco", "Sodio", "pH"]  # declared only, in order
    assert product["brand"] == {"@type": "Brand", "name": "Vichy"}


def test_ph_carries_no_unit_but_minerals_do():
    props = {p["name"]: p for p in _page()["@graph"][0]["additionalProperty"]}
    assert props["Residuo seco"]["unitText"] == "mg/L"
    assert "unitText" not in props["pH"]


def test_no_price_rating_or_availability_is_ever_claimed():
    """The catalogue holds none of these. Emitting them to chase a rich
    result is how a site earns a manual action."""
    blob = json.dumps(_page())
    for invented in ("offers", "aggregateRating", "review", "priceCurrency"):
        assert invented not in blob


def test_breadcrumbs_route_through_the_province_page():
    """That page now serves real content, so the trail is a real path — and
    it links the ficha to the region listing."""
    crumbs = _page()["@graph"][1]["itemListElement"]
    assert [c["name"] for c in crumbs] == ["Catálogo", "Girona", "Vichy Catalán"]
    assert [c["position"] for c in crumbs] == [1, 2, 3]
    assert crumbs[1]["item"].endswith("/recomendar?lugar=Girona")


def test_a_water_without_a_province_skips_that_crumb():
    crumbs = _page(_water(province=""))["@graph"][1]["itemListElement"]
    assert [c["name"] for c in crumbs] == ["Catálogo", "Vichy Catalán"]
    assert [c["position"] for c in crumbs] == [1, 2]  # renumbered, no gap


def test_a_photoless_water_declares_no_image():
    assert "image" not in _page()["@graph"][0]
    assert _page(_water(photo_url="gs://x.jpg"))["@graph"][0]["image"] == "gs://x.jpg"


def test_a_place_lists_its_waters_in_the_order_shown():
    waters = [_water(id="a", name="A"), _water(id="b", name="B")]
    item_list = seo.place_page("Girona", waters, url=f"{HOME}/x", home_url=HOME)[
        "@graph"
    ][0]
    assert item_list["numberOfItems"] == 2
    assert [i["name"] for i in item_list["itemListElement"]] == ["A", "B"]
    assert item_list["itemListElement"][0]["url"] == f"{HOME}/agua/a"


def test_the_site_claims_no_search_action():
    """The catalogue filter is client-side — there is no search URL to give a
    crawler, and a fabricated one is a broken promise."""
    assert "potentialAction" not in seo.site(HOME)
    assert seo.site(HOME)["inLanguage"] == "es-ES"


def test_first_photo_scans_the_groups_in_order():
    plain, shot = _water(id="a"), _water(id="b", photo_url="gs://b.jpg")
    assert seo.first_photo([plain], [shot]) == "gs://b.jpg"
    assert seo.first_photo([plain], []) == ""
