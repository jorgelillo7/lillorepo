# config.py
import os
import sys

from dotenv import load_dotenv

# Carga las variables del archivo .env si existe (para desarrollo local)
load_dotenv()

SERVICE_ACCOUNT_PATH = "/gdrive_sa/biwenger-tools-sa.json"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
]


# --- CONFIGURACIÓN DE TEMPORADA ---
# Para cambiar de temporada: actualizar TEMPORADA_ACTUAL en deploy.yml (env global)
# o via: gcloud run services update ... --update-env-vars TEMPORADA_ACTUAL=26-27
TEMPORADA_ACTUAL = os.getenv("TEMPORADA_ACTUAL", "25-26")
# Añadir la nueva temporada aquí al inicio de cada año (ver docs/operations.md).
TEMPORADAS_DISPONIBLES = ["24-25", "25-26"]

# NUEVO: Diccionario para mapear temporadas a IDs de Google Sheets
LIGAS_ESPECIALES_SHEETS = {
    "25-26": os.getenv("LIGAS_ESPECIALES_SHEET_ID_25_26"),
    "24-25": os.getenv("LIGAS_ESPECIALES_SHEET_ID_24_25"),
}

# --- NUEVO: Diccionario de Trofeos ---
TROFEOS_SHEETS = {
    "25-26": os.getenv("TROFEOS_SHEET_ID_25_26"),
}


# --- CONFIGURACIÓN (leída desde el entorno) ---
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
CLOUD_RUN_JOB_NAME = os.getenv("CLOUD_RUN_JOB_NAME")
CLOUD_RUN_REGION = os.getenv("CLOUD_RUN_REGION", "europe-southwest1")

# --- SECRETOS DE LA APLICACIÓN ---
# Refuse to start without a SECRET_KEY in production. A predictable default
# (the old "default-dev-key") makes Flask session cookies trivially forgeable,
# so we never want it to silently leak into a real deploy.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if "pytest" in sys.modules:
        # Test suites set their own value on app.config after import; allow
        # module import to succeed so collection doesn't fail.
        SECRET_KEY = "pytest-secret-key-not-for-prod"
    else:
        raise RuntimeError(
            "SECRET_KEY env var is required; refusing to start with a default."
        )

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# --- VERSIÓN DESPLEGADA (short SHA, 7 chars) ---
GIT_COMMIT = os.getenv("GIT_COMMIT", "local")
DEPLOY_TIME = os.getenv("DEPLOY_TIME", "")

# --- CONFIGURACIÓN NO CRÍTICA (valores fijos) ---
MESSAGES_PER_PAGE = 7

# Nombres base de los archivos. La temporada se añadirá dinámicamente.
COMUNICADOS_FILENAME_BASE = "comunicados"
PARTICIPACION_FILENAME_BASE = "participacion"
PALMARES_FILENAME = "palmares.csv"
CLAUSULAZOS_FILENAME_BASE = "clausulazos"
TABLA_JUSTICIA_FILENAME_BASE = "tabla_justicia"
