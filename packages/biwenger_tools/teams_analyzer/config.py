import os
from dotenv import load_dotenv

from core.sdk import biwenger as biwenger_sdk
from core.utils import load_json_secret

load_dotenv()


# Production: BIWENGER_CREDENTIALS_JSON (keys: email, password)
# Production: TELEGRAM_BOT_CONFIG_JSON (keys: bot_token, chat_id)
# Local dev: individual env vars as fallback.
_BIWENGER_CFG = load_json_secret("BIWENGER_CREDENTIALS_JSON")
_TELEGRAM_CFG = load_json_secret("TELEGRAM_BOT_CONFIG_JSON")

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
# JP_AUTH_TOKEN is sourced from the BIWENGER_CREDENTIALS_JSON secret (new key
# `jp_auth_token`) so it stops living in the public git history. Fallback to a
# JP_AUTH_TOKEN env var for local dev. The token belongs to the JP mobile app
# and can't be rotated by us, so this only limits exposure surface — it does
# not "secret-ify" something we own.
JP_AUTH_TOKEN = _BIWENGER_CFG.get("jp_auth_token") or os.getenv("JP_AUTH_TOKEN", "")
JP_COMPETITION = 1  # LaLiga
JP_SCORE_TYPE = 2  # SofaScore (sistema usado por el Automanager)

# --- MODO DE ANÁLISIS ---
# "daily"   → mi equipo + mercado (cron diario)
# "all"     → todos los equipos + mercado (/analizar)
# "my_team" → solo mi equipo (/myTeam)
# "alinear" → auto-alineación Biwenger (/alinear)
ANALYSIS_MODE = os.getenv("ANALYSIS_MODE", "daily")
