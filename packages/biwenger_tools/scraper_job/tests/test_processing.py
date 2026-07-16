from core.domain.models import Clausulazo, LeagueMessage
from packages.biwenger_tools.scraper_job.logic.processing import (
    build_tabla_justicia,
    categorize_title,
    parse_clausulazos,
    process_participation,
    sort_messages,
)


def _msg(autor: str, categoria: str, id_hash: str) -> LeagueMessage:
    return LeagueMessage(
        id_hash=id_hash,
        fecha="",
        autor=autor,
        titulo="",
        contenido="",
        categoria=categoria,
    )


def test_categorize_title():
    assert categorize_title("Crónica - La final") == "cronica"
    assert categorize_title("CRONICAS") == "cronica"
    assert categorize_title("Dato - Venta de jugadores") == "dato"
    assert categorize_title("DATOS - Fichaje millonario") == "dato"
    assert categorize_title("Cesión - Última hora") == "cesion"
    assert categorize_title("Comunicado - La liga comienza") == "comunicado"
    assert categorize_title("Fichajes del mes") == "comunicado"
    assert categorize_title("") == "comunicado"
    assert categorize_title("  noticia sin categoria ") == "comunicado"
    assert categorize_title("Crónica - con acento") == "cronica"
    # Lenient cronica: bare "CRÓNICA" and "CRÓNICA <something>" without dash.
    assert categorize_title("CRÓNICA") == "cronica"
    assert categorize_title("CRÓNICA FINAL") == "cronica"
    assert categorize_title("Crónica jornada 10") == "cronica"
    assert categorize_title("CRÓNICAS Jornada 10") == "cronica"
    # Should NOT match words that merely *start* with the substring.
    assert categorize_title("Cronicado el partido") == "comunicado"


def test_process_participation():
    """Aggregates message IDs per author/category, deduplicating by id_hash."""
    messages = [
        _msg("Autor1", "comunicado", "id1"),
        _msg("Autor2", "dato", "id2"),
        _msg("Autor1", "dato", "id3"),
        _msg("Autor1", "comunicado", "id1"),  # duplicate
        _msg("Autor3", "cronica", "id4"),
        _msg("Reportajes Lloriquin", "cronica", "id5"),
    ]
    # The scraper passes the include_non_playing map, so the cronista is a
    # first-class author here even though he never competes.
    user_map = {
        1: "Autor1",
        2: "Autor2",
        3: "Autor3",
        4: "Autor4",
        13945871: "Reportajes Lloriquin",
    }

    result = process_participation(messages, user_map)
    by_author = {p.autor: p for p in result}

    assert len(result) == 5
    assert by_author["Reportajes Lloriquin"].cronicas == ["id5"]
    assert by_author["Autor1"].comunicados == ["id1"]
    assert by_author["Autor1"].datos == ["id3"]
    assert by_author["Autor2"].comunicados == []
    assert by_author["Autor2"].datos == ["id2"]
    assert by_author["Autor3"].cronicas == ["id4"]
    assert by_author["Autor4"].comunicados == []
    # Property total = sum of all four lists
    assert by_author["Autor1"].total == 2


def test_sort_messages():
    messages = [
        LeagueMessage("h1", "02-01-2024 10:00:00", "", "", "", ""),
        LeagueMessage("h2", "01-01-2024 12:00:00", "", "", "", ""),
        LeagueMessage("h3", "03-01-2024 08:00:00", "", "", "", ""),
        LeagueMessage("h4", "fecha-invalida", "", "", "", ""),
    ]
    sorted_msgs = sort_messages(messages)
    assert sorted_msgs[0].id_hash == "h3"
    assert sorted_msgs[1].id_hash == "h1"
    assert sorted_msgs[2].id_hash == "h2"
    assert sorted_msgs[3].id_hash == "h4"  # invalid date sorts last


def test_parse_clausulazos_with_dict_player():
    raw_data = {
        "data": [
            {
                "date": 1700000000,
                "content": [
                    {
                        "type": "clause",
                        "amount": 5000000,
                        "from": {"name": "Equipo A"},
                        "to": {"name": "Equipo B"},
                        "player": {"id": 1, "name": "Lewandowski"},
                    }
                ],
            }
        ]
    }
    result = parse_clausulazos(raw_data, players_map={})
    assert len(result) == 1
    assert result[0].jugador == "Lewandowski"
    assert result[0].equipo_vendedor == "Equipo A"
    assert result[0].equipo_comprador == "Equipo B"
    assert result[0].precio == 5000000


def test_parse_clausulazos_with_int_player():
    raw_data = {
        "data": [
            {
                "date": 1700000000,
                "content": [
                    {
                        "type": "clause",
                        "amount": 3000000,
                        "from": {"name": "Equipo C"},
                        "to": {"name": "Equipo D"},
                        "player": 42,
                    }
                ],
            }
        ]
    }
    players_map = {42: {"id": 42, "name": "Vinicius Jr."}}
    result = parse_clausulazos(raw_data, players_map=players_map)
    assert len(result) == 1
    assert result[0].jugador == "Vinicius Jr."
    assert result[0].precio == 3000000


def test_parse_clausulazos_skips_non_clause_entries():
    raw_data = {
        "data": [{"date": 1700000000, "content": [{"type": "other", "amount": 1000}]}]
    }
    assert parse_clausulazos(raw_data, players_map={}) == []


def test_build_tabla_justicia():
    clausulazos = [
        Clausulazo("01-01-2025 10:00", "P1", "Equipo B", "Equipo A", 1000),
        Clausulazo("02-01-2025 10:00", "P2", "Equipo B", "Equipo A", 2000),
        Clausulazo("03-01-2025 10:00", "P3", "Equipo A", "Equipo C", 3000),
    ]
    tabla = build_tabla_justicia(clausulazos)
    by_team = {row.equipo: row for row in tabla}

    assert "Equipo A" in by_team
    assert by_team["Equipo A"].total_hechos == 2
    assert by_team["Equipo A"].total_recibidos == 1
    assert by_team["Equipo A"].punto_de_mira == "Equipo B"
    assert by_team["Equipo A"].mayor_agresor == "Equipo C"
    assert by_team["Equipo A"].hechos[0] == ["Equipo B", 2]

    assert by_team["Equipo B"].total_hechos == 0
    assert by_team["Equipo B"].total_recibidos == 2


def test_build_tabla_justicia_empty():
    assert build_tabla_justicia([]) == []
