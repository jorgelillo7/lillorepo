"""HTTP client for the Jornada Perfecta private API.

The mobile app uses a fixed token hardcoded in its JS bundle. The
`fitness-daily` endpoint returns the full La Liga player list with
next-matchday predictions.

JP stamps every `predict` with an `updated_at` (Unix timestamp). We
use those timestamps as a freshness fingerprint: a cheap `limit=5`
probe reads the first five players and takes `max(updated_at)`. If
that matches the cached value, the cached payload is returned without
re-fetching the full list.

JP writes the ~549 players in a ~4.5 min batch window, so each player
has its own `updated_at` inside the batch. Sampling 5 players covers
the case where the top one by `priceIncrement DESC` happens to be a
no-op in the latest refresh (the failure mode that single-player
probing exhibited).
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


_PROBE_SAMPLE_SIZE = 5


def _max_updated_at(players: list[dict], score_type: int) -> Optional[int]:
    """Highest `updated_at` across the given players for `score_type`.

    Returns None if no player in the sample has a usable timestamp.
    """
    timestamps = [_extract_updated_at(p, score_type) for p in players]
    valid = [t for t in timestamps if t is not None]
    return max(valid) if valid else None


def _peek_fingerprint(
    auth_token: str, competition: int, score_type: int
) -> Optional[int]:
    """Lightweight freshness probe: `limit=N` request, returns max timestamp.

    JP writes the league in a batch over a few minutes, so each player's
    `updated_at` is its own value within the batch window. Sampling N
    players and taking the max is a stable fingerprint of the snapshot
    — strictly stronger than reading just the first player (whose
    position by `priceIncrement DESC` shifts between requests).
    """
    params = _build_params(auth_token, competition, score_type)
    params["limit"] = str(_PROBE_SAMPLE_SIZE)
    try:
        response = requests.get(JP_URL, headers=JP_HEADERS, params=params, timeout=10)
        response.raise_for_status()
        players = response.json().get("players") or []
    except (requests.RequestException, ValueError):
        return None
    return _max_updated_at(players, score_type)


def fetch_all_players(
    auth_token: str,
    competition: int = 1,
    score_type: int = 2,
) -> list[dict]:
    """Returns the full JP player list for the given competition + score type.

    On a warm cache, validates freshness via a `limit=5` probe (~200ms)
    and returns the cached payload when JP hasn't refreshed. On a cold
    cache, skips the probe — we'd fetch in full either way.

    Cache fingerprint is `max(updated_at)` across the probe sample; the
    cached payload stores `max(updated_at)` across all ~549 players so
    a strictly increasing snapshot triggers a refetch.
    """
    cache_key = (competition, score_type)
    cached_entry = _CACHE.get(cache_key)

    # Warm-cache path: probe for staleness with a cheap multi-player call.
    if cached_entry is not None:
        cached_fingerprint, cached_players = cached_entry
        current_fingerprint = _peek_fingerprint(auth_token, competition, score_type)
        if (
            current_fingerprint is not None
            and cached_fingerprint == current_fingerprint
        ):
            logger.info(
                "JP players served from cache.",
                extra={
                    "competition": competition,
                    "score_type": score_type,
                    "count": len(cached_players),
                    "fingerprint": cached_fingerprint,
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

    # Use the same `top N by priceIncrement DESC` sample the probe sees,
    # so the next probe's max is comparable to what we cache here.
    fresh_fingerprint = _max_updated_at(players[:_PROBE_SAMPLE_SIZE], score_type)
    _CACHE[cache_key] = (fresh_fingerprint, players)

    logger.info(
        "JP players fetched.",
        extra={"count": len(players), "fingerprint": fresh_fingerprint},
    )
    return players


def get_predict_rate(player: dict, score_type: int = 2) -> Optional[int]:
    """Return the prediction rate for the requested scoring system.

    Returns None when the player has no scheduled match (empty `predict`)
    or the requested score_type is not present.
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
