"""Round-trip tests for domain models (Firestore serialization)."""

from datetime import datetime

from core.constants import MADRID_TZ
from core.domain.models import (
    Clausulazo,
    JusticeEntry,
    LeagueMessage,
    Palmares,
    Participation,
    SeasonStanding,
    _parse_fecha,
)


def test_participation_total_with_empty_lists():
    assert Participation(autor="X").total == 0


# --- Firestore serialization ---------------------------------------------


def test_parse_fecha_known_formats():
    """Both legacy date formats parse; unknown input yields None."""
    assert _parse_fecha("01-06-2025 10:00:00") == datetime(
        2025, 6, 1, 10, 0, 0, tzinfo=MADRID_TZ
    )
    assert _parse_fecha("11-05-2026 00:18") == datetime(
        2026, 5, 11, 0, 18, tzinfo=MADRID_TZ
    )
    assert _parse_fecha("not a date") is None
    assert _parse_fecha("") is None


def test_league_message_firestore_roundtrip():
    """`fecha` is stored as a native timestamp and rendered back to a string;
    the doc id carries the `id_hash`, so it is not a document field."""
    msg = LeagueMessage(
        id_hash="abc123",
        fecha="01-01-2025 10:00:00",
        autor="Jorge",
        titulo="Título",
        contenido="<p>cuerpo</p>",
        categoria="comunicado",
    )
    doc = msg.to_firestore()
    assert "id_hash" not in doc
    assert isinstance(doc["fecha"], datetime)
    parsed = LeagueMessage.from_firestore("abc123", doc)
    assert parsed == msg


def test_league_message_from_firestore_handles_missing_fields():
    parsed = LeagueMessage.from_firestore("h1", {})
    assert parsed.id_hash == "h1"
    assert parsed.fecha == ""
    assert parsed.categoria == ""


def test_participation_firestore_roundtrip():
    """Firestore keeps native arrays plus a derived `total` for queries."""
    p = Participation(
        autor="Jorge",
        comunicados=["id1", "id2"],
        datos=["id3"],
        cesiones=[],
        cronicas=["id4"],
    )
    doc = p.to_firestore()
    assert doc["comunicados"] == ["id1", "id2"]
    assert doc["total"] == 4
    assert "autor" not in doc
    parsed = Participation.from_firestore("Jorge", doc)
    assert parsed == p


def test_clausulazo_firestore_roundtrip():
    """clausulazos timestamps carry no seconds — the minute-precision format
    must round-trip exactly."""
    c = Clausulazo(
        fecha="11-05-2026 00:18",
        jugador="Ionut Radu",
        equipo_vendedor="La Luceneta",
        equipo_comprador="Ferraz fc",
        precio=6_475_000,
    )
    doc = c.to_firestore()
    assert isinstance(doc["fecha"], datetime)
    parsed = Clausulazo.from_firestore("auto-id-ignored", doc)
    assert parsed == c


def test_justice_entry_firestore_roundtrip():
    """hechos/recibidos move from JSON-stringified CSV cells to native arrays
    of maps."""
    entry = JusticeEntry(
        equipo="Ferraz fc",
        total_hechos=3,
        total_recibidos=1,
        punto_de_mira="Rayo Entrebirras",
        mayor_agresor="Kairat FC",
        hechos=[["Rayo Entrebirras", 2], ["Kairat FC", 1]],
        recibidos=[["Kairat FC", 1]],
    )
    doc = entry.to_firestore()
    assert doc["hechos"] == [
        {"team": "Rayo Entrebirras", "count": 2},
        {"team": "Kairat FC", "count": 1},
    ]
    assert "equipo" not in doc
    parsed = JusticeEntry.from_firestore("Ferraz fc", doc)
    assert parsed == entry


def test_palmares_firestore_roundtrip():
    p = Palmares(
        temporada="2023-2024",
        campeon="Jorge",
        subcampeon="Fabio",
        tercero="Albert",
        multas=["Rubén", "Lucen", "Javi"],
        puntuacion="sofascore",
        record_puntos="101 @fabio",
        jornadas_ganadas="18 @jorge",
    )
    doc = p.to_firestore()
    assert "temporada" not in doc
    assert "farolillo" not in doc
    assert doc["multas"] == ["Rubén", "Lucen", "Javi"]
    assert doc["standings_table"] == []
    parsed = Palmares.from_firestore("2023-2024", doc)
    assert parsed == p


def test_palmares_legacy_firestore_doc_merges_farolillo_into_multas():
    """Pre-existing 24-25 / 23-24 Firestore docs persist `farolillo` as a
    separate string field. On read it gets appended to `multas` so callers
    see one ordered list — the legacy field is harmless until those docs
    are re-written."""
    legacy_doc = {
        "campeon": "Fabio",
        "subcampeon": "Jorge",
        "tercero": "Albert",
        "farolillo": "Rubén",
        "multas": ["Alberto", "Lucen"],
        "puntuacion": "sofascore",
    }
    p = Palmares.from_firestore("2024-2025", legacy_doc)
    assert p.multas == ["Alberto", "Lucen", "Rubén"]


def test_season_standing_firestore_roundtrip():
    s = SeasonStanding(
        position=1,
        user_id=7728610,
        team_name="Rayo Entrebirras",
        real_name="Fabio",
        points=2872,
        best_round=120,
        worst_round=44,
        rounds_won=11,
        avg_position=2.8,
    )
    doc = s.to_firestore()
    assert SeasonStanding.from_firestore(doc) == s


def test_palmares_with_standings_table_roundtrip():
    """Palmares carries the per-user table for seasons captured from 26-27 on.
    Legacy seasons leave it empty and the from/to roundtrip still works."""
    p = Palmares(
        temporada="2025-2026",
        campeon="Fabio",
        subcampeon="Lucena",
        tercero="Pablo",
        multas=["Javi", "Ruben", "Alberto"],
        neutros=["Jorge"],
        puntuacion="personalizada",
        record_puntos="120 @fabio",
        jornadas_ganadas="11 @fabio",
        clausulazos_total="109",
        standings_table=[
            SeasonStanding(
                position=1,
                user_id=7728610,
                team_name="Rayo Entrebirras",
                real_name="Fabio",
                points=2872,
                best_round=120,
                rounds_won=11,
                avg_position=2.8,
            ),
            SeasonStanding(
                position=7,
                user_id=0,
                team_name="—",
                real_name="Alberto",
                note="abandono",
            ),
        ],
    )
    doc = p.to_firestore()
    assert doc["clausulazos_total"] == "109"
    assert doc["multas"] == ["Javi", "Ruben", "Alberto"]
    assert doc["neutros"] == ["Jorge"]
    assert "farolillo" not in doc
    assert len(doc["standings_table"]) == 2
    assert doc["standings_table"][1]["note"] == "abandono"
    parsed = Palmares.from_firestore("2025-2026", doc)
    assert parsed == p
