import os
from dotenv import load_dotenv

# Carga las variables del archivo .env para el desarrollo local
load_dotenv()

# --- CONFIGURACIÓN DE TEMPORADA ---
# Para empezar un nuevo año, solo tienes que cambiar este valor (ej. "26-27").
TEMPORADA_ACTUAL = "25-26"

# --- CONFIGURACIÓN CRÍTICA (leída desde el entorno) ---
BIWENGER_EMAIL = os.getenv("BIWENGER_EMAIL")
BIWENGER_PASSWORD = os.getenv("BIWENGER_PASSWORD")
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")

# --- CONFIGURACIÓN NO CRÍTICA (valores fijos) ---
LEAGUE_ID = "340703"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# --- URLs DE LA API DE BIWENGER ---
BASE_URL = "https://biwenger.as.com/api/v2"
LOGIN_URL = f"{BASE_URL}/auth/login"
ACCOUNT_URL = f"{BASE_URL}/account"
LEAGUE_USERS_URL = f"{BASE_URL}/league/{LEAGUE_ID}?fields=standings"
CLAUSULAZOS_URL = f"{BASE_URL}/league/{LEAGUE_ID}/board?type=transfer&fields=*,content(*,player(*))"

BIWENGER_CF_BASE_URL = "https://cf.biwenger.com/api/v2"
ALL_PLAYERS_DATA_URL = f"{BIWENGER_CF_BASE_URL}/competitions/la-liga/data?lang=es&score=100"

# --- NOMBRES BASE DE ARCHIVOS CSV ---
CLAUSULAZOS_FILENAME_BASE = "clausulazos"
TABLA_JUSTICIA_FILENAME_BASE = "tabla_justicia"

# Rutas donde Cloud Run montará los secretos como archivos
BIWENGER_EMAIL_PATH = "/biwenger_email/biwenger-email"
BIWENGER_PASSWORD_PATH = "/biwenger_password/biwenger-password"
GDRIVE_FOLDER_ID_PATH = "/gdrive_folder_id/gdrive-folder-id"
SERVICE_ACCOUNT_PATH = "/gdrive_sa/biwenger-tools-sa.json"
