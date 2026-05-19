import os
from dotenv import load_dotenv

from core.constants import LEAGUE_ID  # re-exported for callers
from core.sdk import biwenger as biwenger_sdk
from core.utils import load_json_secret

_ = LEAGUE_ID  # noqa: F841  (silence unused-import for callers via config.LEAGUE_ID)

# Carga las variables del archivo .env para el desarrollo local
load_dotenv()


# --- CONFIGURACIÓN DE TEMPORADA ---
# Para cambiar de temporada: actualizar TEMPORADA_ACTUAL en deploy.yml (env global)
# o via: gcloud run jobs update ... --update-env-vars TEMPORADA_ACTUAL=26-27
TEMPORADA_ACTUAL = os.getenv("TEMPORADA_ACTUAL", "25-26")

# --- CONFIGURACIÓN CRÍTICA (leída desde el entorno) ---
_BIWENGER_CFG = load_json_secret("BIWENGER_CREDENTIALS_JSON")
BIWENGER_EMAIL = _BIWENGER_CFG.get("email") or os.getenv("BIWENGER_EMAIL")
BIWENGER_PASSWORD = _BIWENGER_CFG.get("password") or os.getenv("BIWENGER_PASSWORD")
GDRIVE_FOLDER_ID = _BIWENGER_CFG.get("gdrive_folder_id") or os.getenv(
    "GDRIVE_FOLDER_ID"
)

# --- TELEGRAM (notificación al acabar) ---
# Both keys live in TELEGRAM_BOT_CONFIG_JSON which we bind to the job in CI.
# If neither is set (e.g. local dev without secret), the scraper still runs;
# the notification just gets skipped.
_TELEGRAM_CFG = load_json_secret("TELEGRAM_BOT_CONFIG_JSON")
TELEGRAM_BOT_TOKEN = (
    _TELEGRAM_CFG.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
).strip()
TELEGRAM_CHAT_ID = (
    _TELEGRAM_CFG.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
).strip()

# --- CONFIGURACIÓN NO CRÍTICA (valores fijos) ---
# LEAGUE_ID re-exported from core.constants at the top of the file.
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
