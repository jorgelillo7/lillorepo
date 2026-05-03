"""Round-trip tests for domain models (CSV serialization)."""

from core.domain.models import Clausulazo, JusticeEntry, LeagueMessage, Participation


def test_league_message_roundtrip():
    msg = LeagueMessage(
        id_hash="abc123",
        fecha="01-01-2025 10:00:00",
        autor="Jorge",
        titulo="Título",
        contenido="<p>cuerpo</p>",
        categoria="comunicado",
    )
    row = msg.to_csv_row()
    assert set(row.keys()) == set(LeagueMessage.CSV_FIELDS)
    parsed = LeagueMessage.from_csv_row(row)
    assert parsed == msg


def test_league_message_from_csv_row_handles_missing_fields():
    """Empty CSV cells become empty strings, not KeyError."""
    parsed = LeagueMessage.from_csv_row({"id_hash": "x"})
    assert parsed.id_hash == "x"
    assert parsed.fecha == ""
    assert parsed.contenido == ""


def test_participation_roundtrip():
    p = Participation(
        autor="Jorge",
        comunicados=["id1", "id2"],
        datos=["id3"],
        cesiones=[],
        cronicas=["id4"],
    )
    row = p.to_csv_row()
    assert row["comunicados"] == "id1;id2"
    assert row["cesiones"] == ""
    parsed = Participation.from_csv_row(row)
    assert parsed == p
    assert parsed.total == 4


def test_participation_total_with_empty_lists():
    assert Participation(autor="X").total == 0


def test_clausulazo_roundtrip():
    c = Clausulazo(
        fecha="01-01-2025 10:00",
        jugador="Vini Jr",
        equipo_vendedor="Real Madrid",
        equipo_comprador="Manchester City",
        precio=200_000_000,
    )
    row = c.to_csv_row()
    assert row["precio"] == 200_000_000
    parsed = Clausulazo.from_csv_row(row)
    assert parsed == c
    # CSV reads back as string; from_csv_row casts:
    parsed_str = Clausulazo.from_csv_row({**row, "precio": "200000000"})
    assert parsed_str.precio == 200_000_000


def test_clausulazo_from_csv_row_handles_missing_precio():
    parsed = Clausulazo.from_csv_row({"fecha": "x", "jugador": "y"})
    assert parsed.precio == 0


def test_justice_entry_roundtrip():
    entry = JusticeEntry(
        equipo="Equipo A",
        total_hechos=3,
        total_recibidos=1,
        punto_de_mira="Equipo B",
        mayor_agresor="Equipo C",
        hechos=[["Equipo B", 2], ["Equipo D", 1]],
        recibidos=[["Equipo C", 1]],
    )
    row = entry.to_csv_row()
    # hechos/recibidos are JSON-encoded for CSV transport
    assert isinstance(row["hechos"], str)
    parsed = JusticeEntry.from_csv_row(row)
    assert parsed == entry


def test_justice_entry_handles_missing_optional_fields():
    parsed = JusticeEntry.from_csv_row({"equipo": "X", "total_hechos": "5"})
    assert parsed.equipo == "X"
    assert parsed.total_hechos == 5
    assert parsed.total_recibidos == 0
    assert parsed.hechos == []
