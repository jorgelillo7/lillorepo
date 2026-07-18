"""Domain model for be_water: a bottled water and its mineral vector."""

from dataclasses import dataclass, field
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
    "silica",
    "nitrates",
    "ph",
]

MINERAL_LABELS = {
    "tds": "Residuo seco",
    "bicarbonates": "Bicarbonatos",
    "chlorides": "Cloruros",
    "sulfates": "Sulfatos",
    "calcium": "Calcio",
    "magnesium": "Magnesio",
    "sodium": "Sodio",
    "potassium": "Potasio",
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


@dataclass
class Water:
    id: str
    name: str
    brand: str
    spring: str
    province: str
    community: str
    country: str = "ES"
    sparkling: bool = False
    minerals: dict = field(default_factory=dict)
    photo_url: Optional[str] = None
    label_photo_url: Optional[str] = None  # raw label shot — verification proof
    # Mineral fields individually confirmed against a bottle label. A fully
    # `verified` water implies every declared field; this list covers the
    # mixed case (Lanjarón: 4 label values + approximations for the rest).
    verified_fields: list = field(default_factory=list)
    # External recognitions, e.g. {"source": "OCU", "label": "Excelente",
    # "url": ...}. Mention-and-link only — never reproduce third-party
    # scores wholesale.
    mentions: list = field(default_factory=list)
    added_by: str = ""
    verified: bool = False

    @property
    def tds(self) -> Optional[float]:
        return self.minerals.get("tds")

    @property
    def mineralization(self) -> str:
        return mineralization_label(self.tds)

    def is_field_verified(self, field_name: str) -> bool:
        """True when this mineral value comes from a bottle label."""
        return self.verified or field_name in self.verified_fields

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
            sparkling=bool(data.get("sparkling", False)),
            minerals=data.get("minerals", {}) or {},
            photo_url=data.get("photo_url"),
            label_photo_url=data.get("label_photo_url"),
            verified_fields=list(data.get("verified_fields", []) or []),
            mentions=list(data.get("mentions", []) or []),
            added_by=data.get("added_by", ""),
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
            "sparkling": self.sparkling,
            "minerals": self.minerals,
            "photo_url": self.photo_url,
            "label_photo_url": self.label_photo_url,
            "verified_fields": self.verified_fields,
            "mentions": self.mentions,
            "added_by": self.added_by,
            "verified": self.verified,
        }
