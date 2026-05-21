import os

from dotenv import load_dotenv

from core.constants import LEAGUE_ID  # re-exported for callers
from core.sdk import biwenger as biwenger_sdk
from core.utils import load_json_secret

_ = LEAGUE_ID  # noqa: F841  (silence unused-import for callers via config.LEAGUE_ID)

# Loads .env for local dev
load_dotenv()


# --- CONFIGURACIÓN DE TEMPORADA ---
# Para cambiar de temporada: actualizar TEMPORADA_ACTUAL en deploy.yml (env global)
# o via: gcloud run jobs update ... --update-env-vars TEMPORADA_ACTUAL=26-27
TEMPORADA_ACTUAL = os.getenv("TEMPORADA_ACTUAL", "25-26")

# --- BIWENGER CREDENTIALS ---
# Prod: BIWENGER_CREDENTIALS_JSON in Secret Manager.
# Local: BIWENGER_EMAIL / BIWENGER_PASSWORD env vars (via .env).
_BIWENGER_CFG = load_json_secret("BIWENGER_CREDENTIALS_JSON")
BIWENGER_EMAIL = _BIWENGER_CFG.get("email") or os.getenv("BIWENGER_EMAIL")
BIWENGER_PASSWORD = _BIWENGER_CFG.get("password") or os.getenv("BIWENGER_PASSWORD")

# --- TELEGRAM (notification on completion) ---
# Both keys live in TELEGRAM_BOT_CONFIG_JSON which we bind to the job in CI.
# Missing creds → notification skipped silently, scraper still runs.
_TELEGRAM_CFG = load_json_secret("TELEGRAM_BOT_CONFIG_JSON")
TELEGRAM_BOT_TOKEN = (
    _TELEGRAM_CFG.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
).strip()
TELEGRAM_CHAT_ID = (
    _TELEGRAM_CFG.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
).strip()

# --- BIWENGER API URLs (derived from core for the user's league) ---
LOGIN_URL = biwenger_sdk.LOGIN_URL
ACCOUNT_URL = biwenger_sdk.ACCOUNT_URL
ALL_PLAYERS_DATA_URL = biwenger_sdk.ALL_PLAYERS_DATA_URL
LEAGUE_USERS_URL = biwenger_sdk.league_standings_url(LEAGUE_ID)
CLAUSULAZOS_URL = biwenger_sdk.clausulazos_url(LEAGUE_ID)
BOARD_MESSAGES_URL = biwenger_sdk.league_board_url(LEAGUE_ID)
