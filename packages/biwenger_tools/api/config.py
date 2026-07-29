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
ADMIN_TRANSFERS_URL = biwenger_sdk.admin_transfers_url(LEAGUE_ID)
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

# --- DRAFT (annual snake draft, see logic/draft.py + logic/draft_service.py) ---
# Season string for the `draft/{season}/...` Firestore layout. Reuses the
# web package's `TEMPORADA_ACTUAL` env var (packages/biwenger_tools/web/config.py)
# so both packages roll over together with a single deploy.yml bump.
DRAFT_SEASON = os.getenv("TEMPORADA_ACTUAL", "26-27")

# Frozen closed-market CSV (see .claude/skills/draft). Read from a public
# bucket object rather than bundled into the image: the `python_service` macro
# only ships `templates/` and `static/`, and re-uploading a corrected export
# must not require a redeploy the night before the draft.
DRAFT_MARKET_CSV_URL = os.getenv(
    "DRAFT_MARKET_CSV_URL",
    "https://storage.googleapis.com/biwenger-special-tournaments"
    f"/draft/{DRAFT_SEASON}/market.csv",
)

# Offline fallback used when `DRAFT_MARKET_CSV_URL` is blank (tests, laptop).
DRAFT_MARKET_CSV_PATH = os.getenv("DRAFT_MARKET_CSV_PATH", "")

# Telegram user id allowed to call `/draft/undo`. Must be a *user* id, which is
# always positive — it cannot be derived from `TELEGRAM_CHAT_ID`, since the
# owner chat is itself a group and so carries a negative id that matches nobody.
DRAFT_ADMIN_TELEGRAM_ID = (
    _TELEGRAM_CFG.get("draft_admin_telegram_id")
    or os.getenv("DRAFT_ADMIN_TELEGRAM_ID", "")
).strip()

# Gate on the Biwenger *writes* the draft makes (`transfer_player` /
# `revert_transfer`). Default False: validation, state and Firestore all
# run normally, but no player ever actually changes hands until this is
# flipped on for the live draft session.
_DRAFT_APPLY_RAW = os.getenv("DRAFT_APPLY_TO_BIWENGER", "false").strip().lower()
DRAFT_APPLY_TO_BIWENGER = _DRAFT_APPLY_RAW in ("1", "true", "yes")
