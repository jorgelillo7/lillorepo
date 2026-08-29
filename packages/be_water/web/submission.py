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
from packages.be_water.web.domain import MINERAL_FIELDS, Water, analysis_is_older

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


_MONTHS = {
    "enero": "01",
    "febrero": "02",
    "marzo": "03",
    "abril": "04",
    "mayo": "05",
    "junio": "06",
    "julio": "07",
    "agosto": "08",
    "septiembre": "09",
    "setiembre": "09",
    "octubre": "10",
    "noviembre": "11",
    "diciembre": "12",
}
_ISO_DATE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?$")
_ES_DATE = re.compile(r"^([a-zñ]+)\s+(\d{4})$")


def normalize_analysis_date(raw: Optional[str]) -> Optional[str]:
    """Label analysis date → "YYYY-MM", or "YYYY" when only a year is given.

    Accepts what the OCR and the form actually produce ("2025-02", "2025",
    "Febrero 2025") and returns None for anything else — a malformed date is
    worse than no date, since it would order wrongly against a real one.
    """
    text = (raw or "").strip().lower()
    if not text:
        return None
    iso = _ISO_DATE.match(text)
    if iso:
        year, month = iso.group(1), iso.group(2)
        return f"{year}-{int(month):02d}" if month and 1 <= int(month) <= 12 else year
    spanish = _ES_DATE.match(unidecode(text).replace("de ", "").strip())
    if spanish and spanish.group(1) in _MONTHS:
        return f"{spanish.group(2)}-{_MONTHS[spanish.group(1)]}"
    return None


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
    analysis_date: Optional[str],
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
        analysis_date=analysis_date,
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
    # A submission that declares no date inherits the one already on file:
    # dropping it would make the next comparison think the ficha is undated.
    water.analysis_date = water.analysis_date or existing.analysis_date
    water.mentions = existing.mentions
    water.verified_fields = sorted(
        set(water.verified_fields) | set(existing.verified_fields)
    )
    # Seeded waters get adopted by whoever backs them with a label; a real
    # user's water keeps its original author.
    if existing.added_by and existing.added_by != "seed":
        water.added_by = existing.added_by
        water.added_at = existing.added_at


def stale_analysis_warning(
    incoming: Optional[str], existing: Optional[Water]
) -> Optional[str]:
    """Message to show when the submitted label is older than the stored one
    (or undated against a dated one), else None. The submission is never
    blocked — the contributor confirms and the previous state is snapshotted."""
    if existing is None or not existing.analysis_date:
        return None
    if not analysis_is_older(incoming, existing.analysis_date):
        return None
    theirs = incoming or "sin fecha"
    return (
        f"Esta ficha ya tiene un análisis de {existing.analysis_date} y el de "
        f"tu etiqueta es {theirs}. Guardar la sustituirá por datos más "
        "antiguos. Puedes guardarla igualmente: se conserva una copia de los "
        "valores actuales para poder revertirla."
    )


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


# --- Where a submitted composition belongs on the timeline -----------------

CURRENT = "current"
HISTORY = "history"
UNDATED = "undated"


def analysis_outcome(incoming: Optional[str], existing: Optional[Water]) -> str:
    """Where this composition goes: `CURRENT`, `HISTORY` or `UNDATED`.

    - `CURRENT` — it is the most recent analysis, so it becomes the ficha's
      composition *and* joins the series. Includes a resubmission of the date
      the ficha already shows, which corrects it in both places.
    - `HISTORY` — it predates what the ficha shows, so it joins the series and
      **leaves the ficha alone**. This is the change: an older label used to
      overwrite the present after a warning, which is how a measurement got
      lost by clicking through a dialog.
    - `UNDATED` — no analysis date, so it has no place on a timeline. It can
      still be the ficha's composition (there may be nothing better), but it
      never enters the series and never displaces a dated one. Three quarters
      of the catalog is in this state: the label is not required to print the
      date.

    Ordering is `domain.analysis_is_older`, unchanged — undated loses to dated,
    and a plain year loses to a month of the same year.
    """
    if not incoming:
        return UNDATED
    if existing is None or not existing.analysis_date:
        return CURRENT
    return HISTORY if analysis_is_older(incoming, existing.analysis_date) else CURRENT
