"""Cliente HTTP para la API privada de Jornada Perfecta.

La app móvil usa un token fijo hardcoded en el bundle JS. El endpoint
fitness-daily devuelve la lista completa de jugadores de LaLiga con sus
predicciones para la próxima jornada.
"""

from typing import Optional

import requests

from core.utils import get_logger

logger = get_logger(__name__)

JP_URL = "https://www.jornadaperfecta.com/api/fitness-daily"
JP_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "user-agent": "AppBlog/Android",
}


def _build_params(
    auth_token: str,
    competition: int,
    score_type: int,
    limit: int = 600,
) -> dict:
    return {
        "auth": auth_token,
        "competition": str(competition),
        "score": str(score_type),
        "offset": "0",
        "limit": str(limit),
        "playerStatus": "all",
        "orderBy": "desc",
        "order": "priceIncrement",
        "showPredict": "true",
    }


def fetch_all_players(
    auth_token: str,
    competition: int = 1,
    score_type: int = 2,
) -> list[dict]:
    """Devuelve la lista completa de jugadores JP para la competición indicada."""
    logger.info(
        "Fetching JP players...",
        extra={"competition": competition, "score_type": score_type},
    )
    params = _build_params(auth_token, competition, score_type)
    response = requests.get(JP_URL, headers=JP_HEADERS, params=params, timeout=30)
    response.raise_for_status()
    players = response.json().get("players", [])
    logger.info("JP players fetched.", extra={"count": len(players)})
    return players


def get_predict_rate(player: dict, score_type: int = 2) -> Optional[int]:
    """Extrae el rate de predicción para el sistema de puntuación dado.

    Devuelve None si el jugador no tiene partido (predict vacío) o el tipo
    pedido no aparece.
    """
    for entry in player.get("predict") or []:
        if entry.get("type") == score_type:
            return entry.get("rate")
    return None


def check_api_health(
    auth_token: str, competition: int = 1, score_type: int = 2
) -> None:
    """Lanza RuntimeError si la API no responde o el token ha rotado."""
    params = {**_build_params(auth_token, competition, score_type), "limit": "1"}
    try:
        response = requests.get(JP_URL, headers=JP_HEADERS, params=params, timeout=15)
    except requests.RequestException as e:
        raise RuntimeError(f"JP API unreachable: {e}") from e

    if response.status_code != 200 or not response.json().get("players"):
        raise RuntimeError(
            f"JP API no responde (HTTP {response.status_code}) — "
            "token posiblemente rotado. Descargar APK nuevo y extraer token con: "
            "unzip -p app.apk assets/index.android.bundle | "
            "strings | grep -o 'lks9k2k[^ \"&]*'"
        )
