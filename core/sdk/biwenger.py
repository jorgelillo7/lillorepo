import json
import re
import requests


class BiwengerClient:
    """
    Cliente para interactuar con la API de Biwenger.
    La configuración (URLs, credenciales) se inyecta al crear una instancia.
    """

    def __init__(self, email, password, login_url, account_url, league_id):
        requests.packages.urllib3.disable_warnings(
            requests.packages.urllib3.exceptions.InsecureRequestWarning
        )
        self.session = requests.Session()
        self.email = email
        self.password = password
        self.login_url = login_url
        self.account_url = account_url
        self.league_id = str(league_id)
        self.user_id = None
        self._authenticate()

    def _authenticate(self):
        """Realiza el proceso de login y configura la sesión con las cabeceras necesarias."""
        print("▶️  Iniciando sesión en Biwenger...")
        login_headers = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "X-Lang": "es",
            "X-Version": "628",
        }
        login_payload = {"email": self.email, "password": self.password}

        login_response = self.session.post(
            self.login_url, data=login_payload, headers=login_headers, verify=False
        )
        login_response.raise_for_status()
        token = login_response.json().get("token")
        if not token:
            raise Exception("Error en el login: No se recibió el token.")
        print("✅ Token de sesión obtenido.")

        self.session.headers.update(login_headers)
        self.session.headers.update({"Authorization": f"Bearer {token}"})

        print("▶️  Obteniendo datos de la cuenta...")
        account_response = self.session.get(self.account_url, verify=False)
        account_response.raise_for_status()
        account_data = account_response.json()

        leagues = account_data.get("data", {}).get("leagues", [])
        for league in leagues:
            if str(league.get("id")) == self.league_id:
                self.user_id = league.get("user", {}).get("id")
                break

        if not self.user_id:
            raise Exception(
                f"Error: No se pudo encontrar el ID de usuario para la liga {self.league_id}."
            )
        print(
            f"✅ ID de usuario ({self.user_id}) para la liga {self.league_id} obtenido."
        )

        self.session.headers.update(
            {"X-League": self.league_id, "X-User": str(self.user_id)}
        )
        self.session.verify = False
        print("✅ Sesión de Biwenger iniciada y configurada.")

    def get_league_users(self, league_users_url):
        """Obtiene el mapa de usuarios (ID -> Nombre) de la liga."""
        print("▶️  Obteniendo lista de usuarios de la liga...")
        response = self.session.get(league_users_url)
        response.raise_for_status()
        standings = response.json().get("data", {}).get("standings", [])
        if not standings:
            return {}
        user_map = {
            int(user["id"]): user["name"] for user in standings if user.get("id")
        }
        print(f"✅ Mapa de {len(user_map)} usuarios creado.")
        return user_map

    def get_board_messages(self, board_messages_url):
        """Obtiene todos los mensajes del tablón de la liga."""
        print(f"▶️  Obteniendo mensajes del tablón...")
        response = self.session.get(board_messages_url)
        response.raise_for_status()
        return response.json()

    def get_all_players_data_map(self, all_players_data_url):
        """Descarga la base de datos completa de jugadores de Biwenger."""
        print("▶️  Descargando la base de datos de jugadores de Biwenger...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
        }
        response = requests.get(all_players_data_url, headers=headers, verify=False)
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
            for player_id, player_info in players_dict.items()
        }
        print(f"✅ Base de datos de Biwenger con {len(players_map)} jugadores creada.")
        return players_map

    def get_manager_squad(self, manager_squad_url_template, manager_id):
        """Obtiene la plantilla de un mánager específico."""
        url = manager_squad_url_template.format(manager_id=manager_id)
        response = self.session.get(url)
        response.raise_for_status()
        return response.json().get("data", {}).get("players", [])

    def get_market_players(self, market_url):
        """Obtiene los jugadores que están actualmente en el mercado."""
        print("▶️  Obteniendo jugadores del mercado...")
        response = self.session.get(market_url)
        response.raise_for_status()
        market_players = response.json().get("data", {}).get("sales", [])
        print(f"✅ Se han encontrado {len(market_players)} jugadores en el mercado.")
        return market_players

    def get_clausulazos(self, clausulazos_url):
        """Obtiene los clausulazos (compras por cláusula) del tablón de la liga."""
        print("▶️  Obteniendo clausulazos...")
        response = self.session.get(clausulazos_url)
        response.raise_for_status()
        data = response.json()
        print(f"✅ Clausulazos obtenidos.")
        return data
