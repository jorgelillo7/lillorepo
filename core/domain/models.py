"""
Domain models for Biwenger Tools.

These dataclasses define the data contracts that flow between services
(scraper_job → store → web). Two serialization formats are supported:

- **CSV** — the legacy Google Drive format. ``CSV_FIELDS`` is the canonical
  column order; ``from_csv_row``/``to_csv_row`` handle fields encoded as
  joined strings or JSON.
- **Firestore** — ``from_firestore``/``to_firestore`` map a model to a
  Firestore document. Native types are used where the CSV had to encode
  (arrays instead of ``;``-joined strings, nested maps instead of JSON
  strings, real timestamps instead of ``dd-MM-YYYY`` text).

The dataclass field types are the contract callers rely on; both formats
(de)serialize to the *same* in-memory shape. In particular ``fecha`` is
always a display string on the model — Firestore stores it as a native
timestamp, but ``from_firestore`` renders it back to a string so templates
and sorting code keep working unchanged.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Optional, Tuple

from core.constants import MADRID_TZ

# Date formats seen across the legacy CSVs, most specific first.
# comunicados uses seconds; clausulazos does not.
_FECHA_FORMATS: Tuple[str, ...] = (
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%d",
)


def _split_ids(raw: str) -> list:
    return raw.split(";") if raw else []


def _parse_fecha(raw) -> Optional[datetime]:
    """Parse a legacy date string into a Madrid-tz datetime.

    Returns None when the value is empty or matches no known format — the
    caller decides what to store as a fallback.
    """
    if not raw or not isinstance(raw, str):
        return None
    for fmt in _FECHA_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=MADRID_TZ)
        except (ValueError, TypeError):
            continue
    return None


def _format_fecha(value, fmt: str) -> str:
    """Render a Firestore timestamp as a display string in Madrid time.

    Passes strings through untouched so the function is safe to call on a
    value that was never converted to a timestamp.
    """
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.astimezone(MADRID_TZ).strftime(fmt)


def _fecha_for_firestore(raw: str):
    """Convert a display date string to a value for a Firestore document.

    Returns a timezone-aware datetime when the string parses (Firestore
    stores it as a native timestamp), otherwise the raw string so no data
    is silently lost.
    """
    return _parse_fecha(raw) or raw


@dataclass
class LeagueMessage:
    """A single message posted on the league board."""

    id_hash: str
    fecha: str
    autor: str
    titulo: str
    contenido: str
    categoria: str  # "comunicado" | "dato" | "cronica" | "cesion"

    CSV_FIELDS: ClassVar[Tuple[str, ...]] = (
        "id_hash",
        "fecha",
        "autor",
        "titulo",
        "contenido",
        "categoria",
    )
    # Display format for `fecha` when read back from a Firestore timestamp.
    _FECHA_FMT: ClassVar[str] = "%d-%m-%Y %H:%M:%S"

    @classmethod
    def from_csv_row(cls, row: dict) -> "LeagueMessage":
        return cls(**{k: row.get(k, "") for k in cls.CSV_FIELDS})

    def to_csv_row(self) -> dict:
        return {
            "id_hash": self.id_hash,
            "fecha": self.fecha,
            "autor": self.autor,
            "titulo": self.titulo,
            "contenido": self.contenido,
            "categoria": self.categoria,
        }

    @classmethod
    def from_firestore(cls, doc_id: str, data: dict) -> "LeagueMessage":
        """Build from a Firestore doc. The doc id is the `id_hash`."""
        return cls(
            id_hash=doc_id,
            fecha=_format_fecha(data.get("fecha"), cls._FECHA_FMT),
            autor=data.get("autor", ""),
            titulo=data.get("titulo", ""),
            contenido=data.get("contenido", ""),
            categoria=data.get("categoria", ""),
        )

    def to_firestore(self) -> dict:
        """Document fields. The `id_hash` is the doc id, not a field."""
        return {
            "fecha": _fecha_for_firestore(self.fecha),
            "autor": self.autor,
            "titulo": self.titulo,
            "contenido": self.contenido,
            "categoria": self.categoria,
        }


@dataclass
class Participation:
    """Aggregate message IDs per author per category."""

    autor: str
    comunicados: list = field(default_factory=list)
    datos: list = field(default_factory=list)
    cesiones: list = field(default_factory=list)
    cronicas: list = field(default_factory=list)

    CSV_FIELDS: ClassVar[Tuple[str, ...]] = (
        "autor",
        "comunicados",
        "datos",
        "cesiones",
        "cronicas",
    )

    @classmethod
    def from_csv_row(cls, row: dict) -> "Participation":
        return cls(
            autor=row.get("autor", ""),
            comunicados=_split_ids(row.get("comunicados", "")),
            datos=_split_ids(row.get("datos", "")),
            cesiones=_split_ids(row.get("cesiones", "")),
            cronicas=_split_ids(row.get("cronicas", "")),
        )

    def to_csv_row(self) -> dict:
        return {
            "autor": self.autor,
            "comunicados": ";".join(self.comunicados),
            "datos": ";".join(self.datos),
            "cesiones": ";".join(self.cesiones),
            "cronicas": ";".join(self.cronicas),
        }

    @classmethod
    def from_firestore(cls, doc_id: str, data: dict) -> "Participation":
        """Build from a Firestore doc. The doc id is the `autor`."""
        return cls(
            autor=doc_id,
            comunicados=list(data.get("comunicados", [])),
            datos=list(data.get("datos", [])),
            cesiones=list(data.get("cesiones", [])),
            cronicas=list(data.get("cronicas", [])),
        )

    def to_firestore(self) -> dict:
        """Document fields — native arrays, plus a derived `total` for queries.

        The `autor` is the doc id, not a field.
        """
        return {
            "comunicados": self.comunicados,
            "datos": self.datos,
            "cesiones": self.cesiones,
            "cronicas": self.cronicas,
            "total": self.total,
        }

    @property
    def total(self) -> int:
        return (
            len(self.comunicados)
            + len(self.datos)
            + len(self.cesiones)
            + len(self.cronicas)
        )


@dataclass
class Clausulazo:
    """A player transfer executed via release clause."""

    fecha: str
    jugador: str
    equipo_vendedor: str
    equipo_comprador: str
    precio: int

    CSV_FIELDS: ClassVar[Tuple[str, ...]] = (
        "fecha",
        "jugador",
        "equipo_vendedor",
        "equipo_comprador",
        "precio",
    )
    # clausulazos timestamps carry no seconds.
    _FECHA_FMT: ClassVar[str] = "%d-%m-%Y %H:%M"

    @classmethod
    def from_csv_row(cls, row: dict) -> "Clausulazo":
        return cls(
            fecha=row.get("fecha", ""),
            jugador=row.get("jugador", ""),
            equipo_vendedor=row.get("equipo_vendedor", ""),
            equipo_comprador=row.get("equipo_comprador", ""),
            precio=int(row.get("precio", 0) or 0),
        )

    def to_csv_row(self) -> dict:
        return {
            "fecha": self.fecha,
            "jugador": self.jugador,
            "equipo_vendedor": self.equipo_vendedor,
            "equipo_comprador": self.equipo_comprador,
            "precio": self.precio,
        }

    @classmethod
    def from_firestore(cls, doc_id: str, data: dict) -> "Clausulazo":
        """Build from a Firestore doc. Clausulazos use auto-ids — `doc_id`
        is not part of the model and is ignored."""
        return cls(
            fecha=_format_fecha(data.get("fecha"), cls._FECHA_FMT),
            jugador=data.get("jugador", ""),
            equipo_vendedor=data.get("equipo_vendedor", ""),
            equipo_comprador=data.get("equipo_comprador", ""),
            precio=int(data.get("precio", 0) or 0),
        )

    def to_firestore(self) -> dict:
        return {
            "fecha": _fecha_for_firestore(self.fecha),
            "jugador": self.jugador,
            "equipo_vendedor": self.equipo_vendedor,
            "equipo_comprador": self.equipo_comprador,
            "precio": self.precio,
        }


@dataclass
class JusticeEntry:
    """Transfer attack/defense statistics for a single team."""

    equipo: str
    total_hechos: int
    total_recibidos: int
    punto_de_mira: str  # team that buys from this team the most
    mayor_agresor: str  # team that sells to this team the most
    # Lists of (team, count) tuples, sorted descending by count. Lists rather
    # than dicts because order matters in the UI and CSV serialization.
    hechos: list = field(default_factory=list)
    recibidos: list = field(default_factory=list)

    CSV_FIELDS: ClassVar[Tuple[str, ...]] = (
        "equipo",
        "total_hechos",
        "total_recibidos",
        "punto_de_mira",
        "mayor_agresor",
        "hechos",
        "recibidos",
    )

    @classmethod
    def from_csv_row(cls, row: dict) -> "JusticeEntry":
        return cls(
            equipo=row.get("equipo", ""),
            total_hechos=int(row.get("total_hechos", 0) or 0),
            total_recibidos=int(row.get("total_recibidos", 0) or 0),
            punto_de_mira=row.get("punto_de_mira", "—"),
            mayor_agresor=row.get("mayor_agresor", "—"),
            hechos=json.loads(row.get("hechos", "[]") or "[]"),
            recibidos=json.loads(row.get("recibidos", "[]") or "[]"),
        )

    def to_csv_row(self) -> dict:
        return {
            "equipo": self.equipo,
            "total_hechos": self.total_hechos,
            "total_recibidos": self.total_recibidos,
            "punto_de_mira": self.punto_de_mira,
            "mayor_agresor": self.mayor_agresor,
            "hechos": json.dumps(self.hechos, ensure_ascii=False),
            "recibidos": json.dumps(self.recibidos, ensure_ascii=False),
        }

    @staticmethod
    def _pairs_to_maps(pairs: list) -> list:
        """[[team, count], ...] → [{"team": team, "count": count}, ...]."""
        return [{"team": t, "count": int(c)} for t, c in pairs]

    @staticmethod
    def _maps_to_pairs(maps: list) -> list:
        """[{"team": team, "count": count}, ...] → [[team, count], ...]."""
        return [[m.get("team", ""), int(m.get("count", 0))] for m in maps]

    @classmethod
    def from_firestore(cls, doc_id: str, data: dict) -> "JusticeEntry":
        """Build from a Firestore doc. The doc id is the `equipo`."""
        return cls(
            equipo=doc_id,
            total_hechos=int(data.get("total_hechos", 0) or 0),
            total_recibidos=int(data.get("total_recibidos", 0) or 0),
            punto_de_mira=data.get("punto_de_mira", "—"),
            mayor_agresor=data.get("mayor_agresor", "—"),
            hechos=cls._maps_to_pairs(data.get("hechos", [])),
            recibidos=cls._maps_to_pairs(data.get("recibidos", [])),
        )

    def to_firestore(self) -> dict:
        """Document fields — `hechos`/`recibidos` as native arrays of maps
        instead of the JSON-stringified mess the CSV needed. The `equipo`
        is the doc id, not a field."""
        return {
            "total_hechos": self.total_hechos,
            "total_recibidos": self.total_recibidos,
            "punto_de_mira": self.punto_de_mira,
            "mayor_agresor": self.mayor_agresor,
            "hechos": self._pairs_to_maps(self.hechos),
            "recibidos": self._pairs_to_maps(self.recibidos),
        }


@dataclass
class Palmares:
    """Historical honours for a single season.

    The legacy ``palmares.csv`` stores one ``temporada,categoria,valor`` row
    per honour, so a season spans several rows; ``multa`` in particular
    appears more than once. This model collapses a season into one document
    — the shape Firestore stores under ``palmares/{temporada}``.
    """

    temporada: str
    campeon: str = ""
    subcampeon: str = ""
    tercero: str = ""
    farolillo: str = ""
    multas: list = field(default_factory=list)
    puntuacion: str = ""
    record_puntos: str = ""
    jornadas_ganadas: str = ""

    FIRESTORE_FIELDS: ClassVar[Tuple[str, ...]] = (
        "campeon",
        "subcampeon",
        "tercero",
        "farolillo",
        "puntuacion",
        "record_puntos",
        "jornadas_ganadas",
    )

    @classmethod
    def from_csv_rows(cls, rows: list) -> list["Palmares"]:
        """Collapse the flat ``temporada,categoria,valor`` CSV into one
        ``Palmares`` per season. Unknown categories are ignored by the
        caller's discretion — log them at the call site if needed."""
        by_season: dict[str, "Palmares"] = {}
        for row in rows:
            temporada = (row.get("temporada") or "").strip()
            categoria = (row.get("categoria") or "").strip()
            valor = (row.get("valor") or "").strip()
            if not temporada or not categoria:
                continue
            entry = by_season.setdefault(temporada, cls(temporada=temporada))
            if categoria == "multa":
                entry.multas.append(valor)
            elif categoria in cls.FIRESTORE_FIELDS:
                setattr(entry, categoria, valor)
        return list(by_season.values())

    @classmethod
    def from_firestore(cls, doc_id: str, data: dict) -> "Palmares":
        """Build from a Firestore doc. The doc id is the `temporada`."""
        entry = cls(temporada=doc_id, multas=list(data.get("multas", [])))
        for f in cls.FIRESTORE_FIELDS:
            setattr(entry, f, data.get(f, ""))
        return entry

    def to_firestore(self) -> dict:
        """Document fields. The `temporada` is the doc id, not a field."""
        doc = {f: getattr(self, f) for f in self.FIRESTORE_FIELDS}
        doc["multas"] = self.multas
        return doc
