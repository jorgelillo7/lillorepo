"""
Domain models for Biwenger Tools.

These dataclasses define the data contracts that flow between services
(scraper_job → CSV → web). CSV_FIELDS on each class is the canonical
field order; from_dict() provides typed construction from csv.DictReader rows.
"""
from dataclasses import dataclass, field
from typing import ClassVar, Tuple


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
        "id_hash", "fecha", "autor", "titulo", "contenido", "categoria"
    )

    @classmethod
    def from_dict(cls, row: dict) -> "LeagueMessage":
        return cls(**{k: row[k] for k in cls.CSV_FIELDS})


@dataclass
class Participation:
    """Aggregate message IDs per author per category."""

    autor: str
    comunicados: list = field(default_factory=list)
    datos: list = field(default_factory=list)
    cesiones: list = field(default_factory=list)
    cronicas: list = field(default_factory=list)

    CSV_FIELDS: ClassVar[Tuple[str, ...]] = (
        "autor", "comunicados", "datos", "cesiones", "cronicas"
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
        "fecha", "jugador", "equipo_vendedor", "equipo_comprador", "precio"
    )

    @classmethod
    def from_dict(cls, row: dict) -> "Clausulazo":
        return cls(
            fecha=row["fecha"],
            jugador=row["jugador"],
            equipo_vendedor=row["equipo_vendedor"],
            equipo_comprador=row["equipo_comprador"],
            precio=int(row["precio"]),
        )


@dataclass
class JusticeEntry:
    """Transfer attack/defense statistics for a single team."""

    equipo: str
    total_hechos: int
    total_recibidos: int
    punto_de_mira: str   # team that buys from this team the most
    mayor_agresor: str   # team that sells to this team the most
    hechos: dict = field(default_factory=dict)    # {team: count} — outgoing transfers
    recibidos: dict = field(default_factory=dict) # {team: count} — incoming transfers

    CSV_FIELDS: ClassVar[Tuple[str, ...]] = (
        "equipo", "total_hechos", "total_recibidos",
        "punto_de_mira", "mayor_agresor", "hechos", "recibidos",
    )
