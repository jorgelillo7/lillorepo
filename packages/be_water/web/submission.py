"""Add-water submission logic: pure helpers pulled out of the route so the
slug, duplicate-guard, mineral-parsing, merge and verification rules are
unit-testable without a Flask request.

The route (`app.add_water`) stays responsible for the request/response shape
(CSRF, rate limits, which form to re-render); everything that transforms data
lives here.
"""

import re
from datetime import datetime, timezone
from typing import Mapping, Optional

from unidecode import unidecode

from packages.be_water.web import geo, provenance
from packages.be_water.web.domain import MINERAL_FIELDS, Water

_SLUG_RE = re.compile(r"[^a-z0-9]+")

MAX_FIELD_LEN = 80
MAX_MINERAL_VALUE = 100_000  # mg/L — beyond this it's not water


def form_field(form: Mapping, name: str) -> str:
    """Trimmed, length-capped form value — nobody's manantial needs 80+ chars."""
    return (form.get(name) or "").strip()[:MAX_FIELD_LEN]


def _tokens(text: str) -> set[str]:
    return set(_SLUG_RE.sub(" ", unidecode(text).lower()).split())


def slugify(name: str) -> str:
    """`Lanjarón` → `lanjaron` (unidecode first, so the duplicate guard hits an
    existing doc instead of slugging to `lanjar-n`)."""
    return _SLUG_RE.sub("-", unidecode(name).lower()).strip("-")


def springs_differ(submitted: str, current: str) -> bool:
    """True when both springs are declared and neither's token set contains the
    other's — genuinely different sources, not spelling drift."""
    a, b = _tokens(submitted), _tokens(current)
    return bool(a) and bool(b) and not (a <= b or b <= a)


def similar_water(name: str, catalog: list[Water]) -> Optional[Water]:
    """Fuzzy duplicate guard: token-subset match on normalized names, so
    "Naturis" flags «Naturis (Lidl) — Albacete». Exact slugs are handled
    upstream; near-misses come back for the user to decide."""
    tokens = _tokens(name)
    if not tokens:
        return None
    for water in catalog:
        for candidate in (water.name, water.brand):
            cand = _tokens(candidate)
            if cand and (tokens <= cand or cand <= tokens):
                return water
    return None


def disambiguated_id(water_id: str, spring: str) -> str:
    """A new water sharing an exact name gets its id disambiguated by the spring
    tokens the name doesn't already carry."""
    extra = [t for t in _tokens(spring) if t not in water_id]
    return f"{water_id}-{'-'.join(extra)}" if extra else water_id


def parse_minerals(form: Mapping) -> dict:
    """Numeric mineral fields from the form, comma-normalised and range-guarded."""
    minerals: dict = {}
    for field in MINERAL_FIELDS:
        raw = (form.get(field) or "").strip().replace(",", ".")
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if 0 <= value <= MAX_MINERAL_VALUE:
            minerals[field] = value
    return minerals


def verified_fields_from_ocr(ocr_fields: str, minerals: dict) -> list[str]:
    """Label-declared mineral fields (human-reviewed) become verified_fields."""
    return sorted(f for f in ocr_fields.split(",") if f in minerals)


def build_water(
    form: Mapping,
    *,
    water_id: str,
    name: str,
    minerals: dict,
    verified_fields: list[str],
    photo_url: Optional[str],
    label_photo_url: Optional[str],
    added_by: str,
) -> Water:
    """The submitted water before any merge with an existing doc."""
    province = form_field(form, "province")
    return Water(
        id=water_id,
        name=name,
        brand=form_field(form, "brand") or name,
        spring=form_field(form, "spring"),
        province=province,
        # Derived when the form leaves it blank: the place search matches
        # province *or* community, so a water with only a province is
        # invisible to a community search. An unknown province yields "",
        # same as before.
        community=form_field(form, "community") or geo.community_of(province),
        sparkling=form.get("sparkling") == "on",
        minerals=minerals,
        photo_url=photo_url,
        label_photo_url=label_photo_url,
        verified_fields=verified_fields,
        added_by=added_by,
        added_at=datetime.now(timezone.utc).isoformat(),
    )


def apply_existing(
    water: Water, existing: Water, *, merge_into: bool, form_has_brand: bool
) -> None:
    """Fold an existing unverified doc into the reviewed submission: the form
    wins, everything it can't carry survives from the current doc."""
    if merge_into:
        # Confirmed fuzzy match: the canonical display name stays.
        water.name = existing.name
        water.retailer = existing.retailer
    water.minerals = {**existing.minerals, **water.minerals}
    water.sparkling = water.sparkling or existing.sparkling
    water.spring = water.spring or existing.spring
    water.province = water.province or existing.province
    water.community = water.community or existing.community
    if not form_has_brand:
        water.brand = existing.brand or water.brand
    water.photo_url = water.photo_url or existing.photo_url
    water.label_photo_url = water.label_photo_url or existing.label_photo_url
    water.mentions = existing.mentions
    water.verified_fields = sorted(
        set(water.verified_fields) | set(existing.verified_fields)
    )
    # Seeded waters get adopted by whoever backs them with a label; a real
    # user's water keeps its original author.
    if existing.added_by and existing.added_by != "seed":
        water.added_by = existing.added_by
        water.added_at = existing.added_at


def finalize_provenance(water: Water, existing: Optional[Water]) -> None:
    """Record per-field sources and auto-promote to verified when a label photo
    backs every declared mineral (data-frozen against the monthly sync)."""
    water.sources = provenance.sources_on_save(
        water.minerals,
        water.verified_fields,
        existing.sources if existing is not None else {},
    )
    if (
        water.label_photo_url
        and water.minerals
        and set(water.minerals) <= set(water.verified_fields)
    ):
        water.verified = True
