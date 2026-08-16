"""Structured data for the public pages.

Pure functions returning schema.org dictionaries the templates dump as
JSON-LD. Kept out of the routes so what we claim about a water is unit-tested
rather than eyeballed in a `<script>` tag.

Only facts already on the page are emitted. No ratings, no prices, no
availability — the catalogue holds none of them, and inventing them is how a
site earns a manual action.
"""

from packages.be_water.web.domain import MINERAL_LABELS, Water

_CONTEXT = "https://schema.org"

# Values worth publishing as machine-readable properties, in reading order.
_PROPERTY_FIELDS = [
    "tds",
    "bicarbonates",
    "chlorides",
    "sulfates",
    "calcium",
    "magnesium",
    "sodium",
    "ph",
]


def _properties(water: Water) -> list[dict]:
    """Declared minerals as PropertyValue entries. pH carries no unit."""
    return [
        {
            "@type": "PropertyValue",
            "name": MINERAL_LABELS.get(field, field),
            "value": water.minerals[field],
            **({} if field == "ph" else {"unitText": "mg/L"}),
        }
        for field in _PROPERTY_FIELDS
        if water.minerals.get(field) is not None
    ]


def _breadcrumbs(items: list[tuple[str, str]]) -> dict:
    """`[(name, url), …]` → a BreadcrumbList, positions from 1."""
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": url}
            for i, (name, url) in enumerate(items, start=1)
        ],
    }


def water_page(water: Water, url: str, home_url: str, place_url: str) -> dict:
    """A water's ficha: what it is, plus where it sits in the site."""
    product: dict = {
        "@type": "Product",
        "name": water.name,
        "category": "Agua mineral natural",
        "url": url,
        "description": (
            f"{water.name}: agua mineral de {water.province or 'origen no declarado'}, "
            f"mineralización {water.mineralization}."
        ),
    }
    if water.brand:
        product["brand"] = {"@type": "Brand", "name": water.brand}
    if water.photo_url:
        product["image"] = water.photo_url
    properties = _properties(water)
    if properties:
        product["additionalProperty"] = properties

    trail = [("Catálogo", home_url)]
    if water.province:
        trail.append((water.province, place_url))
    trail.append((water.name, url))

    return {"@context": _CONTEXT, "@graph": [product, _breadcrumbs(trail)]}


def place_page(place: str, waters: list[Water], url: str, home_url: str) -> dict:
    """A region listing: the waters it holds, in the order shown."""
    return {
        "@context": _CONTEXT,
        "@graph": [
            {
                "@type": "ItemList",
                "name": f"Aguas minerales de {place}",
                "numberOfItems": len(waters),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i,
                        "name": water.name,
                        "url": f"{home_url}/agua/{water.id}",
                    }
                    for i, water in enumerate(waters, start=1)
                ],
            },
            _breadcrumbs([("Catálogo", home_url), (place, url)]),
        ],
    }


def site(home_url: str) -> dict:
    """The site itself. No SearchAction: the catalogue filter is client-side,
    so there is no search URL to hand a crawler."""
    return {
        "@context": _CONTEXT,
        "@type": "WebSite",
        "name": "Be Water",
        "url": home_url,
        "inLanguage": "es-ES",
        "description": (
            "Catálogo abierto de aguas minerales españolas: composición, "
            "procedencia y aguas parecidas a la tuya."
        ),
    }


def first_photo(*groups: list[Water]) -> str:
    """First available photo across the given groups — the share preview for
    a page that is about a list rather than one bottle."""
    for waters in groups:
        for water in waters:
            if water.photo_url:
                return water.photo_url
    return ""
