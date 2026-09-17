"""Reader for Analítica Fantasy's Oráculo — the second opinion beside JP.

Two sources, because neither covers the other's half:

- **`/api/v1/oraculo/{league}`** takes the scoring system as a query parameter
  resolved server-side and answers with the eight recommendation lists, the
  matchday and a `generatedAt`. It is the only route that can be *asked* for
  Biwenger scoring, and it echoes back what it served — which this module
  verifies rather than trusts.
- **`/biwenger/predicciones`** is a page, not an endpoint: its numbers live in
  the Next.js RSC flight payload embedded in the HTML. It covers the whole
  squad, which the API's highlights do not.

The scoring system is the trap this module exists to avoid. The same player
reads 7.38 under LaLiga Fantasy and 3.60 under Biwenger, so a source read
through the wrong one looks healthy while halving every projection.

Nothing here decides anything. A failure raises `OraculoError`, never an empty
list: "no opinion on anybody" and "the read broke" call for opposite responses
and must not look alike.
"""

import json
import re
import time
from typing import Iterable, Optional

import requests

from core.utils import get_logger

logger = get_logger(__name__)

LA_LIGA = 140
SISTEMA_BIWENGER = "biwenger-sofascore"

_API_HOST = "https://server.analiticafantasy.com"
PREDICTIONS_URL = "https://www.analiticafantasy.com/biwenger/predicciones"

# Identifies itself on purpose. The site keeps the ability to see, rate-limit
# or block this reader, which is what separates reading from hiding — and there
# is nothing to imitate in any case: the endpoint asks for no headers at all.
USER_AGENT = (
    "lillorepo-biwenger-tools/1.0 "
    "(personal non-commercial fantasy helper; jorge.lillo9@gmail.com)"
)
_HEADERS = {"accept": "application/json", "user-agent": USER_AGENT}

# The model retrains hourly, so a shorter cache buys nothing and spends
# someone else's bandwidth. Per-process, like `jp._CACHE`: losing it on a cold
# start costs one extra read.
CACHE_TTL_SECONDS = 3600
_CACHE: dict = {}

_TIMEOUT = 30

# `self.__next_f.push([1, "<chunk>"])` — the page's data, one JSON string per
# chunk, concatenated in order. The fragile half of this module, isolated so a
# framework change breaks one test instead of the service.
_FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,\s*("(?:[^"\\]|\\.)*")\]\)')


class OraculoError(Exception):
    """The read failed, or served something other than what was asked for."""


def picks_url(league_id: int = LA_LIGA) -> str:
    return f"{_API_HOST}/api/v1/oraculo/{league_id}"


def _get(url: str, params: Optional[dict] = None) -> requests.Response:
    try:
        response = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise OraculoError(f"Oráculo read failed: {url}") from exc


def _cached(key: str, produce):
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
        return hit[1]
    value = produce()
    _CACHE[key] = (time.monotonic(), value)
    return value


def fetch_picks(league_id: int = LA_LIGA, sistema: str = SISTEMA_BIWENGER) -> dict:
    """The eight recommendation lists, the matchday and when it was generated.

    Raises if the echoed `sistema` is not the one asked for. That check is the
    reason to prefer this route at all: it is the only one that can be asked,
    and an unverified answer would be worth less than no answer.
    """

    def produce() -> dict:
        body = _get(picks_url(league_id), {"sistema": sistema}).json()
        data = (body or {}).get("data") or {}
        served = data.get("sistema")
        if served != sistema:
            raise OraculoError(
                f"Oráculo served sistema={served!r}, asked for {sistema!r}"
            )
        logger.info(
            "Oráculo picks read.",
            extra={
                "matchday": data.get("matchday"),
                "sistema": served,
                "model": data.get("modelTag"),
            },
        )
        return {
            "matchday": data.get("matchday"),
            "generated_at": data.get("generatedAt"),
            "model_tag": data.get("modelTag"),
            "picks": data.get("picks") or {},
            "fixtures": data.get("fixtures") or [],
        }

    return _cached(f"picks:{league_id}:{sistema}", produce)


def lists_for(picks_result: dict, player_id: int) -> list[str]:
    """Which recommendation lists a player appears in, in a stable order."""
    picks = picks_result.get("picks") or {}
    return sorted(
        name
        for name, entries in picks.items()
        if any(entry.get("playerId") == player_id for entry in entries or [])
    )


def matchday_dates(picks_result: dict) -> set[str]:
    """The `YYYY-MM-DD` dates this matchday's fixtures are played on.

    The page route carries two matchdays at once; these are what separate them.
    """
    return {
        fixture["fixtureDate"][:10]
        for fixture in picks_result.get("fixtures") or []
        if fixture.get("fixtureDate")
    }


def _flight_payload(html: str) -> str:
    chunks = _FLIGHT.findall(html or "")
    if not chunks:
        raise OraculoError(
            "No RSC flight payload in the predictions page — the site's "
            "rendering changed, or something other than the page was served"
        )
    return "".join(json.loads(chunk) for chunk in chunks)


def _objects(payload: str, key: str) -> list[dict]:
    """Every JSON object in `payload` that opens with `key`.

    Brace-matched rather than parsed: the flight payload is a stream of
    fragments, not one document, so there is nothing to hand to `json.loads`.
    """
    found: list[dict] = []
    for match in re.finditer(r'\{"' + re.escape(key) + r'":', payload):
        start, depth = match.start(), 0
        for index in range(start, len(payload)):
            if payload[index] == "{":
                depth += 1
            elif payload[index] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        found.append(json.loads(payload[start : index + 1]))
                    except json.JSONDecodeError:
                        pass
                    break
    return found


def fetch_predictions() -> list[dict]:
    """Every player row the predictions page carries, both matchdays.

    A row with `predictedPoints == 0` is kept: the site shows `Esperado 0.00`
    for a player it expects not to play, and that is an answer. Dropping it
    would be indistinguishable from Oráculo not carrying him at all.
    """

    def produce() -> list[dict]:
        html = _get(PREDICTIONS_URL).text
        rows = {
            row["playerId"]: row
            for row in _objects(_flight_payload(html), "playerId")
            if row.get("playerId") is not None
        }
        if not rows:
            raise OraculoError("Predictions page carried no player rows")
        logger.info("Oráculo predictions read.", extra={"rows": len(rows)})
        return list(rows.values())

    return _cached("predictions", produce)


def rows_for_dates(rows: Iterable[dict], dates: set[str]) -> list[dict]:
    """Rows whose fixture falls on one of `dates` — one matchday's worth."""
    return [row for row in rows if (row.get("fixtureDate") or "")[:10] in dates]
