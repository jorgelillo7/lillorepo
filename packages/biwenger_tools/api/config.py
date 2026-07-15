import os

from dotenv import load_dotenv

from core.constants import LEAGUE_ID  # re-exported for callers
from core.sdk import biwenger as biwenger_sdk
from core.utils import load_json_secret

_ = LEAGUE_ID  # noqa: F841  (silence unused-import for callers via config.LEAGUE_ID)

load_dotenv()


# Production secrets:
#   BIWENGER_CREDENTIALS_JSON  → email, password, jp_auth_token
#   TELEGRAM_BOT_CONFIG_JSON   → bot_token, chat_id
# Local dev: individual env vars as fallback.
_BIWENGER_CFG = load_json_secret("BIWENGER_CREDENTIALS_JSON")
_TELEGRAM_CFG = load_json_secret("TELEGRAM_BOT_CONFIG_JSON")

BIWENGER_EMAIL = _BIWENGER_CFG.get("email") or os.getenv("BIWENGER_EMAIL", "")
BIWENGER_PASSWORD = _BIWENGER_CFG.get("password") or os.getenv("BIWENGER_PASSWORD", "")
TELEGRAM_BOT_TOKEN = (
    _TELEGRAM_CFG.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN", "")
).strip()
TELEGRAM_CHAT_ID = (
    _TELEGRAM_CFG.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID", "")
).strip()

# --- BIWENGER API URLs (derived from core for the user's league) ---
LOGIN_URL = biwenger_sdk.LOGIN_URL
ACCOUNT_URL = biwenger_sdk.ACCOUNT_URL
MARKET_URL = biwenger_sdk.MARKET_URL
LINEUP_URL = biwenger_sdk.LINEUP_URL
ALL_PLAYERS_DATA_URL = biwenger_sdk.ALL_PLAYERS_DATA_URL
LEAGUE_DATA_URL = biwenger_sdk.league_standings_url(LEAGUE_ID)
USER_SQUAD_URL = biwenger_sdk.manager_squad_url("{manager_id}")
CLAUSULAZOS_URL = biwenger_sdk.clausulazos_url(LEAGUE_ID)
OFFERS_URL = biwenger_sdk.OFFERS_URL

# --- JORNADA PERFECTA (private API) ---
# Token sourced from BIWENGER_CREDENTIALS_JSON.jp_auth_token — it belongs to
# the JP mobile app and can't be rotated by us, but we keep it out of git.
JP_AUTH_TOKEN = _BIWENGER_CFG.get("jp_auth_token") or os.getenv("JP_AUTH_TOKEN", "")
JP_COMPETITION = 1  # LaLiga
JP_SCORE_TYPE = 2  # SofaScore (Automanager system)

# --- AUTO-BID PAUSE (daily digest only) ---
# While today (Madrid) is before this ISO date, the daily digest skips the
# auto-bid step. The manual `POST /market/auto-bid` (bot's /pujar) always
# works. Empty string = never paused. Override via env without a deploy:
#   gcloud run services update biwenger-api --update-env-vars AUTO_BID_PAUSED_UNTIL=...
AUTO_BID_PAUSED_UNTIL = os.getenv("AUTO_BID_PAUSED_UNTIL", "2026-09-01")

# --- GCP TARGETS (the api needs to trigger the scraper Cloud Run Job) ---
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "biwenger-tools")
CLOUD_RUN_REGION = os.getenv("CLOUD_RUN_REGION", "europe-southwest1")
SCRAPER_JOB_NAME = os.getenv("SCRAPER_JOB_NAME", "biwenger-scraper-data")

# Deployed version metadata (set by CI, see deploy.yml). Used by /version.
GIT_COMMIT = os.getenv("GIT_COMMIT", "local")
DEPLOY_TIME = os.getenv("DEPLOY_TIME", "")
