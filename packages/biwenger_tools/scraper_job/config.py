import os
from dotenv import load_dotenv

from core.sdk import biwenger as biwenger_sdk

# Carga las variables del archivo .env para el desarrollo local
load_dotenv()

# --- CONFIGURACIÓN DE TEMPORADA ---
# Para cambiar de temporada: actualizar TEMPORADA_ACTUAL en deploy.yml (env global)
# o via: gcloud run jobs update ... --update-env-vars TEMPORADA_ACTUAL=26-27
TEMPORADA_ACTUAL = os.getenv("TEMPORADA_ACTUAL", "25-26")

# --- CONFIGURACIÓN CRÍTICA (leída desde el entorno) ---
BIWENGER_EMAIL = os.getenv("BIWENGER_EMAIL")
BIWENGER_PASSWORD = os.getenv("BIWENGER_PASSWORD")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")

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

# Rutas donde Cloud Run montará los secretos como archivos
BIWENGER_EMAIL_PATH = "/biwenger_email/biwenger-email"
BIWENGER_PASSWORD_PATH = "/biwenger_password/biwenger-password"
GDRIVE_FOLDER_ID_PATH = "/gdrive_folder_id/gdrive-folder-id"
SERVICE_ACCOUNT_PATH = "/gdrive_sa/biwenger-tools-sa.json"
