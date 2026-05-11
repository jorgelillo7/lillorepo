import json
import os
from dotenv import load_dotenv

from core.sdk import biwenger as biwenger_sdk

# Carga las variables del archivo .env para el desarrollo local
load_dotenv()


def _load_json_secret(env_var: str) -> dict:
    raw = os.getenv(env_var, "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# --- CONFIGURACIÓN DE TEMPORADA ---
# Para cambiar de temporada: actualizar TEMPORADA_ACTUAL en deploy.yml (env global)
# o via: gcloud run jobs update ... --update-env-vars TEMPORADA_ACTUAL=26-27
TEMPORADA_ACTUAL = os.getenv("TEMPORADA_ACTUAL", "25-26")

# --- CONFIGURACIÓN CRÍTICA (leída desde el entorno) ---
_BIWENGER_CREDS = _load_json_secret("BIWENGER_CREDENTIALS_JSON")
BIWENGER_EMAIL = _BIWENGER_CREDS.get("email") or os.getenv("BIWENGER_EMAIL")
BIWENGER_PASSWORD = _BIWENGER_CREDS.get("password") or os.getenv("BIWENGER_PASSWORD")
GDRIVE_FOLDER_ID = _BIWENGER_CREDS.get("gdrive_folder_id") or os.getenv("GDRIVE_FOLDER_ID")

# --- CONFIGURACIÓN NO CRÍTICA (valores fijos) ---
LEAGUE_ID = "340703"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# --- URLs DE LA API DE BIWENGER (constantes en core; deriva las de la liga) ---
LOGIN_URL = biwenger_sdk.LOGIN_URL
ACCOUNT_URL = biwenger_sdk.ACCOUNT_URL
ALL_PLAYERS_DATA_URL = biwenger_sdk.ALL_PLAYERS_DATA_URL
LEAGUE_USERS_URL = biwenger_sdk.league_standings_url(LEAGUE_ID)
CLAUSULAZOS_URL = biwenger_sdk.clausulazos_url(LEAGUE_ID)
BOARD_MESSAGES_URL = biwenger_sdk.league_board_url(LEAGUE_ID)

# --- NOMBRES BASE DE ARCHIVOS CSV ---
CLAUSULAZOS_FILENAME_BASE = "clausulazos"
TABLA_JUSTICIA_FILENAME_BASE = "tabla_justicia"

# Ruta donde Cloud Run monta la Service Account key como archivo (no cambia)
SERVICE_ACCOUNT_PATH = "/gdrive_sa/biwenger-tools-sa.json"
