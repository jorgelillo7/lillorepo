import json
import os
from dotenv import load_dotenv

from core.sdk import biwenger as biwenger_sdk

load_dotenv()


def _load_json_secret(env_var: str) -> dict:
    raw = os.getenv(env_var, "{}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# Production: BIWENGER_CREDENTIALS_JSON (keys: email, password)
# Production: TELEGRAM_BOT_CONFIG_JSON (keys: bot_token, chat_id)
# Local dev: individual env vars as fallback.
_BIWENGER_CFG = _load_json_secret("BIWENGER_CREDENTIALS_JSON")
_TELEGRAM_CFG = _load_json_secret("TELEGRAM_BOT_CONFIG_JSON")

BIWENGER_EMAIL = _BIWENGER_CFG.get("email") or os.getenv("BIWENGER_EMAIL")
BIWENGER_PASSWORD = _BIWENGER_CFG.get("password") or os.getenv("BIWENGER_PASSWORD")
TELEGRAM_BOT_TOKEN = (
    _TELEGRAM_CFG.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
).strip()
TELEGRAM_CHAT_ID = (
    _TELEGRAM_CFG.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
).strip()

# --- CONFIGURACIÓN NO CRÍTICA (valores fijos) ---
LEAGUE_ID = "340703"

# --- URLs DE LA API DE BIWENGER (desde core; deriva las dependientes de la liga) ---
LOGIN_URL = biwenger_sdk.LOGIN_URL
ACCOUNT_URL = biwenger_sdk.ACCOUNT_URL
MARKET_URL = biwenger_sdk.MARKET_URL
LINEUP_URL = biwenger_sdk.LINEUP_URL
ALL_PLAYERS_DATA_URL = biwenger_sdk.ALL_PLAYERS_DATA_URL
LEAGUE_DATA_URL = biwenger_sdk.league_standings_url(LEAGUE_ID)
USER_SQUAD_URL = biwenger_sdk.manager_squad_url("{manager_id}")

# --- JORNADA PERFECTA (API privada) ---
JP_AUTH_TOKEN = "lks9k2k$iJK"
JP_COMPETITION = 1  # LaLiga
JP_SCORE_TYPE = 2  # SofaScore (sistema usado por el Automanager)

# --- MODO DE ANÁLISIS ---
# "daily"   → mi equipo + mercado (cron diario)
# "all"     → todos los equipos + mercado (/analizar)
# "my_team" → solo mi equipo (/myTeam)
# "alinear" → auto-alineación Biwenger (/alinear)
ANALYSIS_MODE = os.getenv("ANALYSIS_MODE", "daily")
