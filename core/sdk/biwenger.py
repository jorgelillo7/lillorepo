"""Biwenger API client."""

import json
import re
import time
from typing import Optional, Union

import requests

from core.utils import get_logger

logger = get_logger(__name__)

# Backoff schedule (seconds) for transient network failures on the lineup PUT.
# Biwenger has occasionally dropped TCP mid-response — when that happens, the
# right move is to retry rather than fail the whole `/alinear` flow.
_LINEUP_RETRY_BACKOFFS = (2, 5, 10)

# --- URLs públicas del API de Biwenger ---
# Cualquier paquete puede importar estas constantes en lugar de redefinirlas.
BIWENGER_API_BASE = "https://biwenger.as.com/api/v2"
BIWENGER_CF_BASE = "https://cf.biwenger.com/api/v2"

LOGIN_URL = f"{BIWENGER_API_BASE}/auth/login"
ACCOUNT_URL = f"{BIWENGER_API_BASE}/account"
MARKET_URL = f"{BIWENGER_API_BASE}/market"
OFFERS_URL = f"{BIWENGER_API_BASE}/offers"
LINEUP_URL = f"{BIWENGER_API_BASE}/user?fields=*,lineup(date)"
ALL_PLAYERS_DATA_URL = f"{BIWENGER_CF_BASE}/competitions/la-liga/data?lang=es&score=100"


def league_url(league_id: Union[str, int]) -> str:
    return f"{BIWENGER_API_BASE}/league/{league_id}"


def league_standings_url(league_id: Union[str, int]) -> str:
    return f"{league_url(league_id)}?fields=standings"


def league_board_url(league_id: Union[str, int], type_filter: str = "text") -> str:
    return f"{league_url(league_id)}/board?type={type_filter}"


def clausulazos_url(league_id: Union[str, int]) -> str:
    return f"{league_url(league_id)}/board?type=transfer&fields=*,content(*,player(*))"


def manager_squad_url(manager_id: Union[str, int]) -> str:
    return f"{BIWENGER_API_BASE}/user/{manager_id}?fields=players(id,owner(*))"


class BiwengerClient:
    """
    Client for the Biwenger API.
    All configuration (URLs, credentials) is injected at construction time.
    """

    DEFAULT_PAGE_LIMIT = 200

    def __init__(
        self,
        email: str,
        password: str,
        login_url: str,
        account_url: str,
        league_id: Union[str, int],
    ) -> None:
        self.session = requests.Session()
        self.email = email
        self.password = password
        self.login_url = login_url
        self.account_url = account_url
        self.league_id = str(league_id)
        self.user_id: Optional[int] = None
        self._authenticate()

    def _authenticate(self) -> None:
        """Logs in and configures the session with the required headers."""
        logger.info("Authenticating with Biwenger...")
        login_headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
            "X-Lang": "es",
            "X-Version": "628",
        }
        login_payload = {"email": self.email, "password": self.password}

        login_response = self.session.post(
            self.login_url, data=login_payload, headers=login_headers
        )
        login_response.raise_for_status()
        token = login_response.json().get("token")
        if not token:
            raise Exception("Login failed: no token received.")
        logger.info("Session token obtained.")

        self.session.headers.update(login_headers)
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        logger.info("Fetching account data...")
        account_response = self.session.get(self.account_url)
        account_response.raise_for_status()
        account_data = account_response.json()

        leagues = account_data.get("data", {}).get("leagues", [])
        for league in leagues:
            if str(league.get("id")) == self.league_id:
                self.user_id = league.get("user", {}).get("id")
                break

        if not self.user_id:
            raise Exception(f"Could not find user ID for league {self.league_id}.")
        logger.info(
            "User ID obtained.",
            extra={"user_id": self.user_id, "league_id": self.league_id},
        )

        self.session.headers.update(
            {"X-League": self.league_id, "X-User": str(self.user_id)}
        )
        logger.info("Biwenger session ready.")

    def get_account_state(
        self,
        squad: Optional[list] = None,
        all_players: Optional[dict] = None,
    ) -> dict:
        """Returns the user's current cash balance and max bid for the league.

        Biwenger's `/account` endpoint exposes `balance` (cash) per league but
        NOT `maxBid` — the "Puja máxima" the mobile app shows is computed
        client-side as:

            puja_maxima = cash + 0.25 * sum(player.price for player in squad)

        If a future league setting changes the 25% factor, the drift surfaces
        in `/recomendar`'s `Saldo` header.

        Pass `squad` (list from `get_manager_squad`) and `all_players`
        (dict from `get_all_players_data_map`) to compute max_bid. Without
        them, max_bid is 0 (only cash is returned).
        """
        response = self.session.get(self.account_url)
        response.raise_for_status()
        leagues = response.json().get("data", {}).get("leagues", [])
        for league in leagues:
            if str(league.get("id")) != self.league_id:
                continue
            user = league.get("user", {}) or {}
            cash = int(user.get("balance") or 0)
            max_bid = 0
            if squad is not None and all_players is not None:
                squad_value = sum(
                    int(all_players.get(p.get("id"), {}).get("price") or 0)
                    for p in squad
                )
                max_bid = cash + squad_value // 4  # 25% factor
            return {"cash": cash, "max_bid": max_bid}
        return {"cash": 0, "max_bid": 0}

    def get_league_users(self, league_users_url: str) -> dict:
        """Returns a mapping of user ID → name for the league."""
        logger.info("Fetching league users...")
        response = self.session.get(league_users_url)
        response.raise_for_status()
        standings = response.json().get("data", {}).get("standings", [])
        if not standings:
            return {}
        user_map = {
            int(user["id"]): user["name"] for user in standings if user.get("id")
        }
        logger.info("User map built.", extra={"count": len(user_map)})
        return user_map

    def get_standings_full(self, league_standings_url: str) -> list:
        """Returns the full standings list ordered by final position.

        Each entry is a dict with at least 'position', 'name', and 'points'.
        """
        response = self.session.get(league_standings_url)
        response.raise_for_status()
        standings = response.json().get("data", {}).get("standings", [])
        logger.info("Standings fetched.", extra={"count": len(standings)})
        return standings

    def get_board_messages(self, board_messages_url: str) -> dict:
        """Returns a single page of board messages."""
        response = self.session.get(board_messages_url)
        response.raise_for_status()
        return response.json()

    def get_all_board_messages(
        self, base_url: str, limit: int = DEFAULT_PAGE_LIMIT
    ) -> list:
        """Paginates board messages from `base_url` until exhausted.

        `base_url` already contains the query string up to (but not including)
        `limit`/`offset`, e.g. ".../board?type=text".
        Returns a flat list of message entries.
        """
        all_messages: list = []
        offset = 0
        while True:
            url = f"{base_url}&limit={limit}&offset={offset}"
            data = self.get_board_messages(url)
            messages = data.get("data", [])
            logger.info(
                "Board page fetched.", extra={"offset": offset, "count": len(messages)}
            )
            if not messages:
                break
            all_messages.extend(messages)
            offset += limit
            if len(messages) < limit:
                break
        logger.info("All board messages fetched.", extra={"total": len(all_messages)})
        return all_messages

    def get_all_players_data_map(self, all_players_data_url: str) -> dict:
        """Downloads the full Biwenger player database."""
        logger.info("Downloading Biwenger player database...")
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(all_players_data_url, headers=headers)
        response.raise_for_status()
        try:
            data = response.json()
        except json.JSONDecodeError:
            jsonp_text = response.text
            json_str = re.search(
                r"^\s*jsonp_\d+\((.*)\)\s*$", jsonp_text, re.DOTALL
            ).group(1)
            data = json.loads(json_str)
        players_dict = data.get("data", {}).get("players", {})
        players_map = {
            player_info["id"]: player_info for _, player_info in players_dict.items()
        }
        logger.info("Player database built.", extra={"count": len(players_map)})
        return players_map

    def get_manager_squad(
        self, manager_squad_url_template: str, manager_id: Union[str, int]
    ) -> list:
        """Returns the squad of a specific manager."""
        url = manager_squad_url_template.format(manager_id=manager_id)
        response = self.session.get(url)
        response.raise_for_status()
        return response.json().get("data", {}).get("players", [])

    def get_market_players(self, market_url: str) -> list:
        """Returns the players currently on the transfer market."""
        logger.info("Fetching market players...")
        response = self.session.get(market_url)
        response.raise_for_status()
        market_players = response.json().get("data", {}).get("sales", [])
        logger.info("Market players fetched.", extra={"count": len(market_players)})
        return market_players

    def place_market_bid(
        self, *, player_id: int, amount: int, offers_url: str = OFFERS_URL
    ) -> dict:
        """POST a market bid on a daily-market (computer-owned) player.

        Body shape:
            {"to": null, "type": "purchase",
             "amount": <eur>, "requestedPlayers": [<player_id>]}

        `to=None` is the differentiator for daily-market players. User
        listings use `to=<seller_user_id>`; those are out of scope for
        auto-bid and should be filtered out by the caller.

        Returns the `data` dict from Biwenger's response (includes the
        offer `id`, useful for diagnostics).
        """
        payload = {
            "to": None,
            "type": "purchase",
            "amount": int(amount),
            "requestedPlayers": [int(player_id)],
        }
        logger.info(
            "Placing market bid.",
            extra={"player_id": player_id, "amount": amount},
        )
        response = self.session.post(offers_url, json=payload)
        response.raise_for_status()
        data = response.json().get("data", {}) or {}
        logger.info(
            "Market bid accepted.",
            extra={
                "player_id": player_id,
                "amount": amount,
                "offer_id": data.get("id"),
                "status": data.get("status"),
            },
        )
        return data

    def get_clausulazos(self, clausulazos_url: str) -> dict:
        """Returns a single page of release-clause transfer entries."""
        response = self.session.get(clausulazos_url)
        response.raise_for_status()
        return response.json()

    def get_all_clausulazos(
        self, base_url: str, limit: int = DEFAULT_PAGE_LIMIT
    ) -> dict:
        """Paginates clausulazos from `base_url` until exhausted.

        `base_url` already contains the query string up to (but not including)
        `limit`/`offset`. Returns `{"data": [...]}` to keep parity with the
        single-page response shape.
        """
        all_entries: list = []
        offset = 0
        while True:
            url = f"{base_url}&limit={limit}&offset={offset}"
            data = self.get_clausulazos(url)
            entries = data.get("data", [])
            if isinstance(entries, dict):
                entries = list(entries.values())
            logger.info(
                "Clausulazos page fetched.",
                extra={"offset": offset, "count": len(entries)},
            )
            if not entries:
                break
            all_entries.extend(entries)
            offset += limit
            if len(entries) < limit:
                break
        logger.info("All clausulazos fetched.", extra={"total": len(all_entries)})
        return {"data": all_entries}

    def set_lineup(
        self,
        lineup_url: str,
        formation: str,
        players_id: list,
        reserves_id: list,
        captain: Optional[int],
    ) -> dict:
        """Sets the lineup via PUT. Returns the API response dict.

        `captain=None` (or 0) tells Biwenger to apply the lineup without a
        captain — used when no starter clears the 3M MV cap. Internally we
        send `0`, which matches the "no captain selected" convention the
        Biwenger payload accepts.

        Retries the PUT on transient network errors (Connection reset, read
        timeout, etc.) with the backoff schedule in `_LINEUP_RETRY_BACKOFFS`.
        A 4xx response (e.g. invalid captain) is treated as terminal — those
        won't get better on retry. Only network-level failures are retried.
        """
        payload = {
            "lineup": {
                "type": formation,
                "playersID": players_id,
                "reservesID": reserves_id,
                "captain": captain if captain else 0,
            }
        }
        logger.info(
            "Sending lineup payload.",
            extra={
                "formation": formation,
                "playersID": players_id,
                "reservesID": reserves_id,
                "captain": captain,
            },
        )

        last_exc: Optional[requests.RequestException] = None
        for attempt, backoff in enumerate((0,) + _LINEUP_RETRY_BACKOFFS, start=1):
            if backoff:
                logger.warning(
                    "Lineup PUT transient failure — retrying.",
                    extra={
                        "attempt": attempt,
                        "backoff_s": backoff,
                        "error": str(last_exc),
                    },
                )
                time.sleep(backoff)
            try:
                response = self.session.put(lineup_url, json=payload, timeout=30)
            except requests.RequestException as exc:
                last_exc = exc
                continue

            if not response.ok:
                logger.error(
                    "Lineup PUT returned non-2xx.",
                    extra={
                        "status": response.status_code,
                        "body": response.text[:500],
                    },
                )
                # 4xx is a terminal error (invalid payload, wrong captain, etc.)
                # 5xx is worth retrying — Biwenger backend may recover.
                if 400 <= response.status_code < 500:
                    response.raise_for_status()
                last_exc = requests.HTTPError(
                    f"Biwenger HTTP {response.status_code}", response=response
                )
                continue

            logger.info(
                "Lineup set.",
                extra={"formation": formation, "captain": captain, "attempts": attempt},
            )
            return response.json()

        # Out of retries.
        logger.error(
            "Lineup PUT failed after retries.",
            extra={
                "attempts": len(_LINEUP_RETRY_BACKOFFS) + 1,
                "error": str(last_exc),
            },
        )
        assert last_exc is not None
        raise last_exc
