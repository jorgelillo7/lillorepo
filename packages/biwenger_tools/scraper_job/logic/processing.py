import json
import unidecode
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from core.utils import get_logger

logger = get_logger(__name__)


def categorize_title(title):
    """Clasifica un mensaje según su título."""
    if not title:
        return "comunicado"
    normalized_title = unidecode.unidecode(title.strip().upper())

    if normalized_title.startswith("CRONICA -") or normalized_title.startswith("CRONICAS"):
        return "cronica"
    if normalized_title.startswith("DATO -") or normalized_title.startswith("DATOS -"):
        return "dato"
    if normalized_title.startswith("CESION -"):
        return "cesion"
    return "comunicado"


def process_participation(all_messages, user_map):
    """Calcula y formatea los datos de participación de los usuarios."""
    participation = {
        name: {"comunicado": [], "dato": [], "cesion": [], "cronica": []}
        for name in user_map.values()
    }

    for msg in all_messages:
        author = msg.get("autor")
        category = msg.get("categoria")
        msg_id = msg.get("id_hash")

        if author in participation and category and msg_id:
            if msg_id not in participation[author][category]:
                participation[author][category].append(msg_id)

    output_data = []
    for author, categories in participation.items():
        output_data.append(
            {
                "autor": author,
                "comunicados": ";".join(categories["comunicado"]),
                "datos": ";".join(categories["dato"]),
                "cesiones": ";".join(categories["cesion"]),
                "cronicas": ";".join(categories["cronica"]),
            }
        )
    return output_data


def sort_messages(messages):
    """Ordena una lista de mensajes por fecha, de más reciente a más antiguo."""

    def get_date(msg):
        try:
            return datetime.strptime(msg["fecha"], "%d-%m-%Y %H:%M:%S")
        except (ValueError, TypeError):
            return datetime.min

    messages.sort(key=get_date, reverse=True)
    return messages


def parse_clausulazos(raw_data, players_map):
    """Transforma la respuesta cruda de la API en una lista de dicts normalizados.

    Cada entry puede contener varios clausulazos en su campo 'content'.
    Devuelve lista de dicts con: fecha, jugador, equipo_vendedor, equipo_comprador, precio.
    """
    entries = raw_data.get("data", [])
    if isinstance(entries, dict):
        entries = list(entries.values())

    clausulazos = []
    madrid_tz = ZoneInfo("Europe/Madrid")

    for entry in entries:
        try:
            content = entry.get("content") or []
            clause_items = [c for c in content if c.get("type") == "clause"]
            if not clause_items:
                continue

            timestamp = entry.get("date", 0)
            fecha = datetime.fromtimestamp(timestamp, tz=madrid_tz).strftime(
                "%d-%m-%Y %H:%M"
            )

            for item in clause_items:
                player_data = item.get("player")
                if isinstance(player_data, dict):
                    jugador = player_data.get("name") or f"#{player_data.get('id', '?')}"
                elif player_data is not None:
                    player_id = int(player_data)
                    player_info = players_map.get(player_id, {})
                    jugador = player_info.get("name") or f"#{player_id}"
                else:
                    jugador = "Desconocido"

                from_team = item.get("from") or {}
                equipo_vendedor = from_team.get("name", "—")

                to_team = item.get("to") or {}
                equipo_comprador = to_team.get("name", "—")

                precio = int(item.get("amount", 0))

                clausulazos.append(
                    {
                        "fecha": fecha,
                        "jugador": jugador,
                        "equipo_vendedor": equipo_vendedor,
                        "equipo_comprador": equipo_comprador,
                        "precio": precio,
                    }
                )
        except Exception:
            logger.warning("Error parsing clausulazo entry.", extra={"entry": str(entry)}, exc_info=True)

    return clausulazos


def build_tabla_justicia(clausulazos):
    """Construye el resumen de ataques realizados y recibidos por cada equipo."""
    ataques_hechos = defaultdict(lambda: defaultdict(int))
    ataques_recibidos = defaultdict(lambda: defaultdict(int))
    equipos = set()

    for c in clausulazos:
        comprador = c["equipo_comprador"]
        vendedor = c["equipo_vendedor"]
        if comprador and comprador != "—" and vendedor and vendedor != "—":
            ataques_hechos[comprador][vendedor] += 1
            ataques_recibidos[vendedor][comprador] += 1
            equipos.add(comprador)
            equipos.add(vendedor)

    tabla = []
    for equipo in equipos:
        hechos = dict(ataques_hechos.get(equipo, {}))
        recibidos = dict(ataques_recibidos.get(equipo, {}))
        hechos_sorted = sorted(hechos.items(), key=lambda x: x[1], reverse=True)
        recibidos_sorted = sorted(recibidos.items(), key=lambda x: x[1], reverse=True)
        tabla.append(
            {
                "equipo": equipo,
                "total_hechos": sum(hechos.values()),
                "total_recibidos": sum(recibidos.values()),
                "punto_de_mira": hechos_sorted[0][0] if hechos_sorted else "—",
                "mayor_agresor": recibidos_sorted[0][0] if recibidos_sorted else "—",
                "hechos": json.dumps(hechos_sorted, ensure_ascii=False),
                "recibidos": json.dumps(recibidos_sorted, ensure_ascii=False),
            }
        )

    tabla.sort(key=lambda x: x["total_hechos"], reverse=True)
    return tabla


def get_all_clausulazos(biwenger, base_url, limit=200):
    """Descarga todos los clausulazos con paginación automática."""
    all_entries = []
    offset = 0

    while True:
        url = f"{base_url}&limit={limit}&offset={offset}"
        data = biwenger.get_clausulazos(url)
        entries = data.get("data", [])
        if isinstance(entries, dict):
            entries = list(entries.values())

        logger.info("Clausulazos page fetched.", extra={"offset": offset, "count": len(entries)})

        if not entries:
            break

        all_entries.extend(entries)
        offset += limit

        if len(entries) < limit:
            break

    logger.info("All clausulazos fetched.", extra={"total": len(all_entries)})
    return {"data": all_entries}


def get_all_board_messages(biwenger, base_url, limit=200):
    """Descarga todos los mensajes del board con paginación automática."""
    all_messages = []
    offset = 0

    while True:
        url = f"{base_url}&limit={limit}&offset={offset}"
        data = biwenger.get_board_messages(url)
        messages = data.get("data", [])

        logger.info("Board page fetched.", extra={"offset": offset, "count": len(messages)})

        if not messages:
            break

        all_messages.extend(messages)
        offset += limit

        if len(messages) < limit:
            break

    logger.info("All board messages fetched.", extra={"total": len(all_messages)})
    return all_messages
