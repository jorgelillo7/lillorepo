"""Cliente HTTP para la API privada de Jornada Perfecta.

La app móvil usa un token fijo hardcoded en el bundle JS. El endpoint
fitness-daily devuelve la lista completa de jugadores de LaLiga con sus
predicciones para la próxima jornada.

JP marca cada `predict` con un `updated_at` (Unix timestamp). Usamos ese
campo para invalidar la cache en proceso: un `limit=1` muy barato lee
sólo el primer jugador y compara su `updated_at`; si coincide con lo
cacheado, devolvemos el payload completo de memoria sin volver a pegar a
JP. Asumimos que JP actualiza el `updated_at` de todos los jugadores
para un `score_type` a la vez (consistente con lo que muestra la app —
"última actualización ayer a las 23:59" para toda la liga).
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

# In-process cache. `(competition, score_type) → (updated_at, players)`. Lives
# per Cloud Run instance — losing it on cold start is fine, and not sharing
# across instances just means two instances may each pay one full fetch per
# JP refresh (a couple of seconds for a single-user league).
_CACHE: dict[tuple[int, int], tuple[Optional[int], list[dict]]] = {}


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


def _extract_updated_at(player: dict, score_type: int) -> Optional[int]:
    for entry in player.get("predict") or []:
        if entry.get("type") == score_type:
            return entry.get("updated_at")
    return None


def _peek_updated_at(
    auth_token: str, competition: int, score_type: int
) -> Optional[int]:
    """Lightweight freshness probe: 1-player `limit=1` request.

    Returns the `updated_at` of the first player's prediction for the
    requested `score_type`, or `None` if the API can't be parsed.
    """
    params = _build_params(auth_token, competition, score_type)
    params["limit"] = "1"
    try:
        response = requests.get(JP_URL, headers=JP_HEADERS, params=params, timeout=10)
        response.raise_for_status()
        players = response.json().get("players") or []
    except (requests.RequestException, ValueError):
        return None
    if not players:
        return None
    return _extract_updated_at(players[0], score_type)


def fetch_all_players(
    auth_token: str,
    competition: int = 1,
    score_type: int = 2,
) -> list[dict]:
    """Returns the full JP player list for the given competition + score type.

    On a warm cache, validates freshness via a `limit=1` probe (~200ms)
    and returns the cached payload when JP hasn't refreshed. On a cold
    cache, skips the probe — we'd fetch in full either way.
    """
    cache_key = (competition, score_type)
    cached_entry = _CACHE.get(cache_key)

    # Warm-cache path: probe for staleness with a cheap limit=1 call.
    if cached_entry is not None:
        cached_updated_at, cached_players = cached_entry
        current_updated_at = _peek_updated_at(auth_token, competition, score_type)
        if current_updated_at is not None and cached_updated_at == current_updated_at:
            logger.info(
                "JP players served from cache.",
                extra={
                    "competition": competition,
                    "score_type": score_type,
                    "count": len(cached_players),
                    "updated_at": cached_updated_at,
                },
            )
            return cached_players

    logger.info(
        "Fetching JP players...",
        extra={"competition": competition, "score_type": score_type},
    )
    params = _build_params(auth_token, competition, score_type)
    response = requests.get(JP_URL, headers=JP_HEADERS, params=params, timeout=30)
    response.raise_for_status()
    players = response.json().get("players", [])

    fresh_updated_at = _extract_updated_at(players[0], score_type) if players else None
    _CACHE[cache_key] = (fresh_updated_at, players)

    logger.info(
        "JP players fetched.",
        extra={"count": len(players), "updated_at": fresh_updated_at},
    )
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
