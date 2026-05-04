"""
Domain models for Biwenger Tools.

These dataclasses define the data contracts that flow between services
(scraper_job → CSV → web). CSV_FIELDS on each class is the canonical
field order; from_csv_row()/to_csv_row() handle (de)serialization for
csv.DictReader/csv.DictWriter, including fields encoded as joined
strings or JSON in the CSV format.
"""

import json
from dataclasses import dataclass, field
from typing import ClassVar, Tuple


def _split_ids(raw: str) -> list:
    return raw.split(";") if raw else []


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
