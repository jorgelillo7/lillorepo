"""Biwenger API client."""
import json
import re
from typing import Union

import requests

from core.utils import get_logger

logger = get_logger(__name__)


class BiwengerClient:
    """
    Client for the Biwenger API.
    All configuration (URLs, credentials) is injected at construction time.
    """

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
        self.user_id = None
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
            raise Exception(
                f"Could not find user ID for league {self.league_id}."
            )
        logger.info(
            "User ID obtained.",
            extra={"user_id": self.user_id, "league_id": self.league_id},
        )

        self.session.headers.update(
            {"X-League": self.league_id, "X-User": str(self.user_id)}
        )
        logger.info("Biwenger session ready.")

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

    def get_board_messages(self, board_messages_url: str) -> dict:
        """Returns all messages from the league board."""
        logger.info("Fetching board messages...")
        response = self.session.get(board_messages_url)
        response.raise_for_status()
        return response.json()

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
            player_info["id"]: player_info
            for _, player_info in players_dict.items()
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

    def get_clausulazos(self, clausulazos_url: str) -> dict:
        """Returns release clause transfers from the league board."""
        logger.info("Fetching clausulazos...")
        response = self.session.get(clausulazos_url)
        response.raise_for_status()
        data = response.json()
        logger.info("Clausulazos fetched.")
        return data
