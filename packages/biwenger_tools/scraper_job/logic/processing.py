from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import unidecode

from core.domain.models import Clausulazo, JusticeEntry, LeagueMessage, Participation
from core.utils import get_logger

logger = get_logger(__name__)

MADRID_TZ = ZoneInfo("Europe/Madrid")


def categorize_title(title):
    """Clasifica un mensaje según su título."""
    if not title:
        return "comunicado"
    normalized_title = unidecode.unidecode(title.strip().upper())

    if normalized_title.startswith("CRONICA -") or normalized_title.startswith(
        "CRONICAS"
    ):
        return "cronica"
    if normalized_title.startswith("DATO -") or normalized_title.startswith("DATOS -"):
        return "dato"
    if normalized_title.startswith("CESION -"):
        return "cesion"
    return "comunicado"


def process_participation(messages: list, user_map: dict) -> list:
    """Aggregates message IDs per author per category. Returns list[Participation]."""
    by_author: dict[str, Participation] = {
        name: Participation(autor=name) for name in user_map.values()
    }

    for msg in messages:
        target = by_author.get(msg.autor)
        if not target or not msg.categoria or not msg.id_hash:
            continue
        bucket = {
            "comunicado": target.comunicados,
            "dato": target.datos,
            "cesion": target.cesiones,
            "cronica": target.cronicas,
        }.get(msg.categoria)
        if bucket is None:
            continue
        if msg.id_hash not in bucket:
            bucket.append(msg.id_hash)

    return list(by_author.values())


def sort_messages(messages: list) -> list:
    """Sorts LeagueMessage list by fecha descending (most recent first)."""

    def get_date(msg: LeagueMessage):
        try:
            return datetime.strptime(msg.fecha, "%d-%m-%Y %H:%M:%S")
        except (ValueError, TypeError):
            return datetime.min

    messages.sort(key=get_date, reverse=True)
    return messages


def parse_clausulazos(raw_data: dict, players_map: dict) -> list:
    """Transforma la respuesta cruda de la API en una lista de Clausulazo.

    Cada entry puede contener varios clausulazos en su campo `content`.
    """
    entries = raw_data.get("data", [])
    if isinstance(entries, dict):
        entries = list(entries.values())

    clausulazos: list[Clausulazo] = []

    for entry in entries:
        try:
            content = entry.get("content") or []
            clause_items = [c for c in content if c.get("type") == "clause"]
            if not clause_items:
                continue

            timestamp = entry.get("date", 0)
            fecha = datetime.fromtimestamp(timestamp, tz=MADRID_TZ).strftime(
                "%d-%m-%Y %H:%M"
            )

            for item in clause_items:
                player_data = item.get("player")
                if isinstance(player_data, dict):
                    jugador = (
                        player_data.get("name") or f"#{player_data.get('id', '?')}"
                    )
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
                    Clausulazo(
                        fecha=fecha,
                        jugador=jugador,
                        equipo_vendedor=equipo_vendedor,
                        equipo_comprador=equipo_comprador,
                        precio=precio,
                    )
                )
        except Exception:
            logger.warning(
                "Error parsing clausulazo entry.",
                extra={"entry": str(entry)},
                exc_info=True,
            )

    return clausulazos


def build_tabla_justicia(clausulazos: list) -> list:
    """Construye el resumen de ataques realizados y recibidos por cada equipo.

    Returns list[JusticeEntry] sorted by total_hechos descending.
    """
    ataques_hechos: dict = defaultdict(lambda: defaultdict(int))
    ataques_recibidos: dict = defaultdict(lambda: defaultdict(int))
    equipos: set = set()

    for c in clausulazos:
        comprador = c.equipo_comprador
        vendedor = c.equipo_vendedor
        if comprador and comprador != "—" and vendedor and vendedor != "—":
            ataques_hechos[comprador][vendedor] += 1
            ataques_recibidos[vendedor][comprador] += 1
            equipos.add(comprador)
            equipos.add(vendedor)

    tabla: list[JusticeEntry] = []
    for equipo in equipos:
        hechos = ataques_hechos.get(equipo, {})
        recibidos = ataques_recibidos.get(equipo, {})
        hechos_sorted = sorted(hechos.items(), key=lambda x: x[1], reverse=True)
        recibidos_sorted = sorted(recibidos.items(), key=lambda x: x[1], reverse=True)
        tabla.append(
            JusticeEntry(
                equipo=equipo,
                total_hechos=sum(hechos.values()),
                total_recibidos=sum(recibidos.values()),
                punto_de_mira=hechos_sorted[0][0] if hechos_sorted else "—",
                mayor_agresor=recibidos_sorted[0][0] if recibidos_sorted else "—",
                hechos=[list(t) for t in hechos_sorted],
                recibidos=[list(t) for t in recibidos_sorted],
            )
        )

    tabla.sort(key=lambda x: x.total_hechos, reverse=True)
    return tabla
