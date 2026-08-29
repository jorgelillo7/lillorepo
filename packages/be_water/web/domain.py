"""Domain model for be_water: a bottled water and its mineral vector."""

from dataclasses import dataclass, field, replace
from typing import Optional

# Mineral fields, in display order. Every value is mg/L except ph.
MINERAL_FIELDS = [
    "tds",
    "bicarbonates",
    "chlorides",
    "sulfates",
    "calcium",
    "magnesium",
    "sodium",
    "potassium",
    "fluoride",
    "silica",
    "nitrates",
    "ph",
]

# Form grouping: the seven values almost every label declares, then the
# ones only some labels carry (rendered as an optional section).
MINERAL_FIELDS_MAIN = MINERAL_FIELDS[:7]
MINERAL_FIELDS_EXTRA = MINERAL_FIELDS[7:]

# Where a field's value came from. Label-confirmed fields live in
# `verified_fields` (they drive the ✓); `sources` records the provenance of
# everything else, so the UI can name it ("fabricante" / "AESAN" / "a mano")
# instead of a blanket "sin verificar".
SOURCE_LABEL = "label"
SOURCE_MANUFACTURER = "manufacturer"
SOURCE_AESAN = "aesan"
SOURCE_MANUAL = "manual"

MINERAL_LABELS = {
    "tds": "Residuo seco",
    "bicarbonates": "Bicarbonatos",
    "chlorides": "Cloruros",
    "sulfates": "Sulfatos",
    "calcium": "Calcio",
    "magnesium": "Magnesio",
    "sodium": "Sodio",
    "potassium": "Potasio",
    "fluoride": "Flúor",
    "silica": "Sílice",
    "nitrates": "Nitratos",
    "ph": "pH",
}


def mineralization_label(tds: Optional[float]) -> str:
    """EU classification by dry residue — the primary one-number summary."""
    if tds is None:
        return "desconocida"
    if tds < 50:
        return "muy débil"
    if tds < 500:
        return "débil"
    if tds < 1500:
        return "fuerte"
    return "muy fuerte"


def analysis_is_older(incoming: Optional[str], existing: Optional[str]) -> bool:
    """True when `incoming` predates `existing`, or carries no date while
    `existing` does. An undated analysis never outranks a dated one: the label
    need not print the date, so absence means unknown, and unknown must not
    silently replace a known-newer composition. Dates are "YYYY-MM" or "YYYY",
    so a plain year loses to a month within the same year — less precision
    yields."""
    if not existing:
        return False
    if not incoming:
        return True
    return incoming < existing


@dataclass
class Water:
    id: str
    name: str
    brand: str
    spring: str
    province: str
    community: str
    country: str = "ES"
    # Supermarket own-brand waters ("Naturis" → Lidl): the retailer whose
    # shelves carry it. Often bottled from several springs, one entry each.
    retailer: Optional[str] = None
    sparkling: bool = False
    minerals: dict = field(default_factory=dict)
    photo_url: Optional[str] = None
    label_photo_url: Optional[str] = None  # raw label shot — verification proof
    # Mineral fields individually confirmed against a bottle label. A fully
    # `verified` water implies every declared field; this list covers the
    # mixed case (Lanjarón: 4 label values + approximations for the rest).
    verified_fields: list = field(default_factory=list)
    # Provenance of non-label fields: {field_name: source}. Label fields are
    # not stored here — their source is implied by `verified_fields`.
    sources: dict = field(default_factory=dict)
    # External recognitions, e.g. {"source": "OCU", "label": "Excelente",
    # "url": ...}. Mention-and-link only — never reproduce third-party
    # scores wholesale.
    mentions: list = field(default_factory=list)
    # Date of the lab analysis the label declares ("CNTA Febrero 2025" →
    # "2025-02"), year-only when that is all it prints. Not a mineral: it
    # dates the whole composition block. Labels are not required to carry it
    # (RD 1798/2010 art. 9.2.b mandates the values, not their date), so None
    # is common and never outranks a dated analysis.
    analysis_date: Optional[str] = None
    added_by: str = ""
    added_at: Optional[str] = None  # ISO timestamp; None for seeded waters
    verified: bool = False
    # True when a photo could not be copied out of `uploads/` and the ficha is
    # pointing at the temporary object. That directory is swept on a schedule,
    # so the photo works now and stops working later — this is what makes the
    # water findable before it does.
    photo_promotion_failed: bool = False

    def with_analysis(self, entry: dict) -> "Water":
        """This water as one of its past analyses saw it.

        The composition **and its provenance** are swapped together: minerals,
        which of them a label confirmed, where the rest came from, and the
        photo of that label. Swapping only the numbers would print this year's
        ✓ over another year's values — a verification claim about a label
        nobody in that entry ever photographed.

        Identity, location and photo stay the ficha's: it is the same bottle.
        """
        return replace(
            self,
            minerals=dict(entry.get("minerals") or {}),
            verified_fields=list(entry.get("verified_fields") or []),
            sources=dict(entry.get("sources") or {}),
            label_photo_url=entry.get("label_photo_url"),
            analysis_date=entry.get("analysis_date"),
        )

    @property
    def tds(self) -> Optional[float]:
        return self.minerals.get("tds")

    @property
    def mineralization(self) -> str:
        return mineralization_label(self.tds)

    def source_of(self, field_name: str) -> Optional[str]:
        """Provenance of a field: 'label' when confirmed against a photographed
        label (in `verified_fields`), else the recorded source (manufacturer /
        aesan / manual), or None when unknown."""
        if field_name in self.verified_fields:
            return SOURCE_LABEL
        return self.sources.get(field_name)

    @classmethod
    def from_firestore(cls, doc_id: str, data: dict) -> "Water":
        return cls(
            id=doc_id,
            name=data.get("name", ""),
            brand=data.get("brand", ""),
            spring=data.get("spring", ""),
            province=data.get("province", ""),
            community=data.get("community", ""),
            country=data.get("country", "ES"),
            retailer=data.get("retailer"),
            sparkling=bool(data.get("sparkling", False)),
            minerals=data.get("minerals", {}) or {},
            photo_url=data.get("photo_url"),
            label_photo_url=data.get("label_photo_url"),
            verified_fields=list(data.get("verified_fields", []) or []),
            sources=dict(data.get("sources", {}) or {}),
            mentions=list(data.get("mentions", []) or []),
            analysis_date=data.get("analysis_date"),
            photo_promotion_failed=bool(data.get("photo_promotion_failed")),
            added_by=data.get("added_by", ""),
            added_at=data.get("added_at"),
            verified=bool(data.get("verified", False)),
        )

    def to_firestore(self) -> dict:
        return {
            "name": self.name,
            "brand": self.brand,
            "spring": self.spring,
            "province": self.province,
            "community": self.community,
            "country": self.country,
            "retailer": self.retailer,
            "sparkling": self.sparkling,
            "minerals": self.minerals,
            "photo_url": self.photo_url,
            "label_photo_url": self.label_photo_url,
            "verified_fields": self.verified_fields,
            "sources": self.sources,
            "mentions": self.mentions,
            "analysis_date": self.analysis_date,
            "added_by": self.added_by,
            "added_at": self.added_at,
            "verified": self.verified,
            "photo_promotion_failed": self.photo_promotion_failed,
        }
