"""
Domain models for Biwenger Tools.

These dataclasses define the data contracts that flow between services
(scraper_job → Firestore → web). ``from_firestore``/``to_firestore`` map
each model to a Firestore document; ``fecha`` is rendered to a display
string on the model so templates and sorting code don't need to know
about native timestamps.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Optional, Tuple

from core.constants import MADRID_TZ

# Date formats accepted by `_parse_fecha`, most specific first.
# Comunicados timestamps carry seconds; clausulazos do not.
_FECHA_FORMATS: Tuple[str, ...] = (
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%d",
)


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

    # Display format for `fecha` when read back from a Firestore timestamp.
    _FECHA_FMT: ClassVar[str] = "%d-%m-%Y %H:%M:%S"

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

    # clausulazos timestamps carry no seconds.
    _FECHA_FMT: ClassVar[str] = "%d-%m-%Y %H:%M"

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
    # Lists of (team, count) tuples, sorted descending by count.
    hechos: list = field(default_factory=list)
    recibidos: list = field(default_factory=list)

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
        """Document fields — `hechos`/`recibidos` as native arrays of maps.
        The `equipo` is the doc id, not a field."""
        return {
            "total_hechos": self.total_hechos,
            "total_recibidos": self.total_recibidos,
            "punto_de_mira": self.punto_de_mira,
            "mayor_agresor": self.mayor_agresor,
            "hechos": self._pairs_to_maps(self.hechos),
            "recibidos": self._pairs_to_maps(self.recibidos),
        }


@dataclass
class SeasonStanding:
    """End-of-season per-user row.

    Captured at season close. ``team_name`` is the Biwenger team name at
    capture time (it can drift later if the user renames). ``real_name``
    is resolved via ``LEAGUE_MEMBERS`` from the stable numeric ``user_id``,
    so it survives renames.

    For accounts deleted mid-season the user_id is no longer resolvable
    via Biwenger — emit ``user_id=0`` and fill ``real_name`` and ``note``
    explicitly (e.g. ``note="abandono"``).
    """

    position: int
    user_id: int
    team_name: str
    real_name: str
    points: int = 0
    best_round: int = 0
    worst_round: int = 0
    rounds_won: int = 0
    avg_position: float = 0.0
    note: str = ""

    FIRESTORE_FIELDS: ClassVar[Tuple[str, ...]] = (
        "position",
        "user_id",
        "team_name",
        "real_name",
        "points",
        "best_round",
        "worst_round",
        "rounds_won",
        "avg_position",
        "note",
    )

    @classmethod
    def from_firestore(cls, data: dict) -> "SeasonStanding":
        return cls(
            position=int(data.get("position", 0) or 0),
            user_id=int(data.get("user_id", 0) or 0),
            team_name=data.get("team_name", ""),
            real_name=data.get("real_name", ""),
            points=int(data.get("points", 0) or 0),
            best_round=int(data.get("best_round", 0) or 0),
            worst_round=int(data.get("worst_round", 0) or 0),
            rounds_won=int(data.get("rounds_won", 0) or 0),
            avg_position=float(data.get("avg_position", 0.0) or 0.0),
            note=data.get("note", ""),
        )

    def to_firestore(self) -> dict:
        return {f: getattr(self, f) for f in self.FIRESTORE_FIELDS}


@dataclass
class Palmares:
    """Historical honours for a single season.

    One document per season under ``palmares/{temporada}``. ``multa`` is a
    list (multiple losers can pay), as is ``neutros``; the farolillo lives
    at the tail of ``multas`` and is rendered with a distinct icon at
    template level rather than being a separate field.

    From 26-27 onwards we also capture ``standings_table`` — one
    ``SeasonStanding`` per league member — so the palmarés page can show
    a full per-user breakdown instead of the bare podium. Older seasons
    leave it empty and the template falls back to the legacy podium view.
    """

    temporada: str
    campeon: str = ""
    subcampeon: str = ""
    tercero: str = ""
    multas: list = field(default_factory=list)
    neutros: list = field(default_factory=list)
    puntuacion: str = ""
    record_puntos: str = ""
    jornadas_ganadas: str = ""
    clausulazos_total: str = ""
    standings_table: list = field(default_factory=list)

    FIRESTORE_FIELDS: ClassVar[Tuple[str, ...]] = (
        "campeon",
        "subcampeon",
        "tercero",
        "puntuacion",
        "record_puntos",
        "jornadas_ganadas",
        "clausulazos_total",
    )

    @classmethod
    def from_firestore(cls, doc_id: str, data: dict) -> "Palmares":
        """Build from a Firestore doc. The doc id is the `temporada`.

        Legacy 24-25 / 23-24 docs persist a separate ``farolillo`` string
        field next to ``multas``. Reading merges it into ``multas`` (at the
        end) so callers see a single ordered list — the last entry is the
        farolillo, visually marked at render time. The legacy field stays
        in Firestore until those docs are re-written.
        """
        entry = cls(
            temporada=doc_id,
            multas=list(data.get("multas", [])),
            neutros=list(data.get("neutros", [])),
        )
        for f in cls.FIRESTORE_FIELDS:
            setattr(entry, f, data.get(f, ""))
        legacy_farolillo = (data.get("farolillo") or "").strip()
        if legacy_farolillo and legacy_farolillo not in entry.multas:
            entry.multas.append(legacy_farolillo)
        entry.standings_table = [
            SeasonStanding.from_firestore(row)
            for row in (data.get("standings_table") or [])
        ]
        return entry

    def to_firestore(self) -> dict:
        """Document fields. The `temporada` is the doc id, not a field."""
        doc = {f: getattr(self, f) for f in self.FIRESTORE_FIELDS}
        doc["multas"] = self.multas
        doc["neutros"] = self.neutros
        doc["standings_table"] = [s.to_firestore() for s in self.standings_table]
        return doc
