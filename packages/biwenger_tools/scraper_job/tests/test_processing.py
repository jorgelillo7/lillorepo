import json
import pytest
import unidecode
from datetime import datetime
from freezegun import freeze_time
from unittest.mock import MagicMock

# Se actualiza la importación a absoluta
from packages.biwenger_tools.scraper_job.logic.processing import (
    categorize_title,
    process_participation,
    sort_messages,
    get_all_board_messages,
    parse_clausulazos,
    build_tabla_justicia,
    get_all_clausulazos,
)
from core.sdk.biwenger import BiwengerClient

# --- Tests unitarios para las funciones de lógica ---


def test_categorize_title():
    """Prueba que el título de los mensajes se clasifica correctamente."""
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


def test_process_participation():
    """Prueba que los datos de participación se procesan y formatean correctamente."""
    mock_messages = [
        {"autor": "Autor1", "categoria": "comunicado", "id_hash": "id1"},
        {"autor": "Autor2", "categoria": "dato", "id_hash": "id2"},
        {"autor": "Autor1", "categoria": "dato", "id_hash": "id3"},
        {"autor": "Autor1", "categoria": "comunicado", "id_hash": "id1"},  # Duplicado
        {"autor": "Autor3", "categoria": "cronica", "id_hash": "id4"},
    ]
    mock_user_map = {1: "Autor1", 2: "Autor2", 3: "Autor3", 4: "Autor4"}

    result = process_participation(mock_messages, mock_user_map)
    result_map = {item["autor"]: item for item in result}

    assert len(result) == 4
    assert result_map["Autor1"]["comunicados"] == "id1"
    assert result_map["Autor1"]["datos"] == "id3"
    assert result_map["Autor2"]["comunicados"] == ""
    assert result_map["Autor2"]["datos"] == "id2"
    assert result_map["Autor3"]["cronicas"] == "id4"
    assert result_map["Autor4"]["comunicados"] == ""


def test_sort_messages():
    """Prueba que los mensajes se ordenan por fecha de más reciente a más antiguo."""
    messages = [
        {"fecha": "02-01-2024 10:00:00"},
        {"fecha": "01-01-2024 12:00:00"},
        {"fecha": "03-01-2024 08:00:00"},
        {"fecha": "fecha-invalida"},
    ]
    sorted_messages = sort_messages(messages)
    assert sorted_messages[0]["fecha"] == "03-01-2024 08:00:00"
    assert sorted_messages[1]["fecha"] == "02-01-2024 10:00:00"
    assert sorted_messages[2]["fecha"] == "01-01-2024 12:00:00"
    assert sorted_messages[3]["fecha"] == "fecha-invalida"


def test_parse_clausulazos_with_dict_player():
    """Prueba que se parsean clausulazos cuando el jugador viene como dict."""
    raw_data = {
        "data": [
            {
                "date": 1700000000,
                "type": "transfer",
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
    assert result[0]["jugador"] == "Lewandowski"
    assert result[0]["equipo_vendedor"] == "Equipo A"
    assert result[0]["equipo_comprador"] == "Equipo B"
    assert result[0]["precio"] == 5000000


def test_parse_clausulazos_with_int_player():
    """Prueba que se resuelve el nombre del jugador cuando viene como entero."""
    raw_data = {
        "data": [
            {
                "date": 1700000000,
                "type": "transfer",
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
    assert result[0]["jugador"] == "Vinicius Jr."
    assert result[0]["precio"] == 3000000


def test_parse_clausulazos_skips_non_clause_entries():
    """Prueba que se ignoran entries sin type=clause en content."""
    raw_data = {
        "data": [
            {
                "date": 1700000000,
                "type": "transfer",
                "content": [{"type": "other", "amount": 1000}],
            }
        ]
    }
    result = parse_clausulazos(raw_data, players_map={})
    assert result == []


def test_build_tabla_justicia():
    """Prueba que la tabla de justicia se construye correctamente."""
    clausulazos = [
        {"equipo_comprador": "Equipo A", "equipo_vendedor": "Equipo B", "jugador": "P1", "fecha": "01-01-2025 10:00", "precio": 1000},
        {"equipo_comprador": "Equipo A", "equipo_vendedor": "Equipo B", "jugador": "P2", "fecha": "02-01-2025 10:00", "precio": 2000},
        {"equipo_comprador": "Equipo C", "equipo_vendedor": "Equipo A", "jugador": "P3", "fecha": "03-01-2025 10:00", "precio": 3000},
    ]
    tabla = build_tabla_justicia(clausulazos)
    tabla_map = {row["equipo"]: row for row in tabla}

    assert "Equipo A" in tabla_map
    assert tabla_map["Equipo A"]["total_hechos"] == 2
    assert tabla_map["Equipo A"]["total_recibidos"] == 1
    assert tabla_map["Equipo A"]["punto_de_mira"] == "Equipo B"
    assert tabla_map["Equipo A"]["mayor_agresor"] == "Equipo C"

    # Verifica que hechos y recibidos se serializan como JSON
    hechos = json.loads(tabla_map["Equipo A"]["hechos"])
    assert hechos[0] == ["Equipo B", 2]

    assert tabla_map["Equipo B"]["total_hechos"] == 0
    assert tabla_map["Equipo B"]["total_recibidos"] == 2


def test_build_tabla_justicia_empty():
    """Prueba que build_tabla_justicia devuelve lista vacía con datos vacíos."""
    assert build_tabla_justicia([]) == []


def test_get_all_clausulazos_paginates():
    """Prueba que get_all_clausulazos pagina correctamente hasta agotar resultados."""
    mock_biwenger = MagicMock()
    page1 = {"data": [{"date": i} for i in range(200)]}
    page2 = {"data": [{"date": i} for i in range(50)]}
    mock_biwenger.get_clausulazos.side_effect = [page1, page2]

    result = get_all_clausulazos(mock_biwenger, "http://api/board?type=transfer")
    assert len(result["data"]) == 250
    assert mock_biwenger.get_clausulazos.call_count == 2


def test_get_all_clausulazos_stops_on_empty():
    """Prueba que get_all_clausulazos se detiene al recibir datos vacíos."""
    mock_biwenger = MagicMock()
    mock_biwenger.get_clausulazos.return_value = {"data": []}

    result = get_all_clausulazos(mock_biwenger, "http://api/board?type=transfer")
    assert result["data"] == []
    assert mock_biwenger.get_clausulazos.call_count == 1
