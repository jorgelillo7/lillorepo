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


# "27.02231/BA": a dotted number, then the province letters. Anchored, so
# prose the reader may return instead of a number ("no consta") is rejected.
_REGISTRY_RE = re.compile(r"^(\d{2}\.\d{3,6}\s*/\s*[A-Z]{1,3})$")
_REGISTRY_PREFIX = re.compile(r"^R\.?\s*G\.?\s*S\.?\s*E\.?\s*A\.?\s*A\.?\s*", re.I)


def normalize_registry_id(raw: Optional[str]) -> str:
    """The sanitary registry number as printed, or "" when it is not one.

    A malformed value is worse than none here: it looks like an official key
    and would be trusted as one. The `RGSEAA` prefix is stripped — it names
    the register, it is not part of the number.

    Deliberately **not** used to derive the province. The suffix does appear
    to encode it on the one bottle where it is legible, and one bottle is not
    evidence.
    """
    text = _REGISTRY_PREFIX.sub("", (raw or "").strip()).strip().upper()
    match = _REGISTRY_RE.match(text)
    return match.group(1).replace(" ", "") if match else ""


def merge_label_reads(primary: dict, secondary: Optional[dict]) -> dict:
    """One prefill from two photographed faces of the same bottle.

    The composition shot is `primary` and wins every field it declares: it is
    the photo kept as verification proof, so a value it read is the one the ✓
    will refer to. The second face only fills gaps.

    A gap is `None` or `""` — the reader returns both for a field it could not
    find. `False` is **not** a gap: `sparkling: False` is an answer, and
    treating it as missing would let the other face turn a still water
    sparkling.
    """
    merged = dict(primary)
    for field, value in (secondary or {}).items():
        if merged.get(field) in (None, "") and value not in (None, ""):
            merged[field] = value
    return merged


def verified_fields_from_ocr(ocr_fields: str, minerals: dict) -> list[str]:
    """Label-declared mineral fields (human-reviewed) become verified_fields."""
    return sorted(f for f in ocr_fields.split(",") if f in minerals)


def form_country(form: Mapping) -> str:
    """Country code from the form, defaulting to Spain.

    An unrecognised code becomes Spain rather than creating a water in a
    country the catalog has no name for: the form is public, and `country`
    now decides which geography rules apply, so a junk value would silently
    switch them off.
    """
    code = (form.get("country") or "").strip().upper()
    return code if code in geo.COUNTRIES else geo.SPAIN


def resolve_place(
    province: str, community: str, country: str = geo.SPAIN
) -> tuple[str, str]:
    """Province and community as they should be stored, from what was typed.

    **Outside Spain none of this applies.** There is no autonomous community to
    derive and no province list to check a shift against, so the region is kept
    as typed and the community stays empty. Running the Spanish rules on a
    Portuguese bottle is what put `province='portugal', community='portugal'`
    on a ficha — the country asserted twice, as two things it is not.

    Both are free-text inputs on a public form, and `tramuntana` shows what
    that costs: it reached Firestore with `province="Talarrubias"` — a town in
    Badajoz — and `community="Badajoz"`, a province. The fields were shifted
    one slot, and the water dropped out of every province and community view
    silently, because nothing ever compared them against the lists this repo
    already carries.

    A community that is really a province means exactly that shift, so it is
    read as one. Otherwise the community is derived from the province, which
    the place search needs: it matches province *or* community, so a water
    with only one of the two is invisible to half the searches.

    Text that matches nothing is kept as typed rather than thrown away — a
    village nobody has mapped is still what the contributor saw on the label,
    and `data_audit` is where a human decides. This only ever repairs a
    provable mistake.
    """
    if not geo.is_spain(country):
        return province, ""
    if not geo.community_of(province) and geo.community_of(community):
        province = community
    return province, geo.community_of(province) or community


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
    country = form_country(form)
    province, community = resolve_place(
        form_field(form, "province"), form_field(form, "community"), country
    )
    return Water(
        id=water_id,
        name=name,
        brand=form_field(form, "brand") or name,
        spring=form_field(form, "spring"),
        province=province,
        community=community,
        country=country,
        registry_id=normalize_registry_id(form.get("registry_id")),
        bottler=form_field(form, "bottler"),
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
    water.registry_id = water.registry_id or existing.registry_id
    water.bottler = water.bottler or existing.bottler
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
    backs every declared mineral (data-frozen against the catalog sync)."""
    water.sources = provenance.sources_on_save(
        water.minerals,
        water.verified_fields,
        existing.sources if existing is not None else {},
        water.id,
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
