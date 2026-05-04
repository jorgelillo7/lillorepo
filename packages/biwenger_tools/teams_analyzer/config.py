import os
from dotenv import load_dotenv

from core.sdk import biwenger as biwenger_sdk

# Carga las variables del archivo .env para el desarrollo local
load_dotenv()

# --- CONFIGURACIÓN CRÍTICA (leída desde el entorno) ---
BIWENGER_EMAIL = os.getenv("BIWENGER_EMAIL")
BIWENGER_PASSWORD = os.getenv("BIWENGER_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- CONFIGURACIÓN NO CRÍTICA (valores fijos) ---
LEAGUE_ID = "340703"

# --- URLs DE LA API DE BIWENGER (desde core; deriva las dependientes de la liga) ---
LOGIN_URL = biwenger_sdk.LOGIN_URL
ACCOUNT_URL = biwenger_sdk.ACCOUNT_URL
MARKET_URL = biwenger_sdk.MARKET_URL
ALL_PLAYERS_DATA_URL = biwenger_sdk.ALL_PLAYERS_DATA_URL
LEAGUE_DATA_URL = biwenger_sdk.league_standings_url(LEAGUE_ID)
USER_SQUAD_URL = biwenger_sdk.manager_squad_url("{manager_id}")

# --- JORNADA PERFECTA (API privada) ---
JP_AUTH_TOKEN = "lks9k2k$iJK"
JP_COMPETITION = 1  # LaLiga
JP_SCORE_TYPE = 2  # SofaScore (sistema usado por el Automanager)
