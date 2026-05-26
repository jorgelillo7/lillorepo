"""Biwenger API client."""

import json
import re
from typing import Optional, Union

import requests

from core.sdk.http import retry_http_request
from core.utils import get_logger

logger = get_logger(__name__)

# --- Public Biwenger API URLs ---
# Any package can import these constants instead of redefining them.
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


def league_round_report_url(league_id: Union[str, int], mode: str = "total") -> str:
    """Per-user "Jornadas ganadas" + "Posición media"."""
    return f"{league_url(league_id)}/report/rounds?mode={mode}"


def league_round_points_report_url(
    league_id: Union[str, int], mode: str = "total"
) -> str:
    """Per-user "Puntos" + "Mejor jornada" + "Peor jornada"."""
    return f"{league_url(league_id)}/report/roundPoints?mode={mode}"


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

    def get_report_rows(self, report_url: str) -> list[dict]:
        """Fetch a Biwenger `report/*` endpoint and parse `columns + rows`
        into a list of dicts keyed by column name.

        Biwenger report responses share the shape:
            {"data": {"columns": [{"name": ...}, ...],
                       "rows": [[...], ...]}}

        Row order matches column order. The first column ("Usuario") is
        a user object (`{id, name, icon}`); the rest are scalars whose
        types depend on the report. We keep the raw column names so the
        caller can pull by the same label that the UI uses.
        """
        response = self.session.get(report_url)
        response.raise_for_status()
        payload = response.json().get("data", {}) or {}
        columns = payload.get("columns", []) or []
        rows = payload.get("rows", []) or []
        col_names = [c.get("name", "") for c in columns]
        parsed = [
            {col_names[i]: row[i] for i in range(min(len(col_names), len(row)))}
            for row in rows
        ]
        logger.info(
            "Report rows fetched.",
            extra={"url": report_url, "count": len(parsed)},
        )
        return parsed

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

        Wrapped in `retry_http_request` so a transient Biwenger 5xx /
        network blip doesn't lose a bid the auto-bid loop already
        decided to place. 4xx (player gone, higher bid in, etc.) still
        surfaces immediately so the caller can `skip + continue`.

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
        response = retry_http_request(
            lambda: self.session.post(offers_url, json=payload, timeout=30),
            label="market bid POST",
        )
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

    def place_clausulazo(
        self,
        *,
        player_id: int,
        amount: int,
        seller_user_id: int,
        offers_url: str = OFFERS_URL,
    ) -> dict:
        """POST a clausulazo offer (release-clause buyout of another user's player).

        Body shape (inferred from the response captured on 2026-05-26 and
        the symmetric ``place_market_bid`` body — verify the first time
        this is exercised against Biwenger by inspecting the DevTools
        "Payload" tab):

            {"to": <seller_user_id>, "type": "clause",
             "amount": <eur>, "requestedPlayers": [<player_id>]}

        ``to`` carries the current owner's user id (the seller); the
        ``fromID`` in Biwenger's response is the authenticated buyer.
        ``amount`` must be at least the player's current release clause
        — Biwenger rejects lower amounts with 4xx.

        Returns Biwenger's ``data`` dict (includes ``id``, ``status``,
        ``created`` and the echoed ``fromID``/``toID``/``amount``/``type``).
        """
        payload = {
            "to": int(seller_user_id),
            "type": "clause",
            "amount": int(amount),
            "requestedPlayers": [int(player_id)],
        }
        logger.info(
            "Placing clausulazo.",
            extra={
                "player_id": player_id,
                "amount": amount,
                "seller_user_id": seller_user_id,
            },
        )
        response = retry_http_request(
            lambda: self.session.post(offers_url, json=payload, timeout=30),
            label="clausulazo POST",
        )
        data = response.json().get("data", {}) or {}
        logger.info(
            "Clausulazo accepted.",
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

        Wrapped in `retry_http_request`: 5xx + network errors retry with
        backoff, 4xx (invalid captain, malformed payload) surface
        immediately so the caller can fail fast.
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
        response = retry_http_request(
            lambda: self.session.put(lineup_url, json=payload, timeout=30),
            label="lineup PUT",
        )
        logger.info(
            "Lineup set.",
            extra={"formation": formation, "captain": captain},
        )
        return response.json()
