import os
import sys

from dotenv import load_dotenv

from core.utils import load_json_secret

# Pulls vars from a local .env when present (used for local dev).
load_dotenv()

# --- Firestore ---
# be_water deploys to its own GCP project; core.sdk.firestore honours this.
os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

# --- Application secrets ---
# Prod: FLASK_WEB_CONFIG_JSON bound from Secret Manager (be-water-app).
# Local dev: SECRET_KEY env var (via .env) or the dev default below.
_FLASK_CFG = load_json_secret("FLASK_WEB_CONFIG_JSON")

# Refuse to start without a SECRET_KEY in production (session cookie signing).
SECRET_KEY = _FLASK_CFG.get("secret_key") or os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if "pytest" in sys.modules:
        SECRET_KEY = "pytest-secret-key-not-for-prod"
    elif os.getenv("K_SERVICE"):  # only enforce on Cloud Run
        raise RuntimeError(
            "SECRET_KEY env var is required; refusing to start with a default."
        )
    else:
        SECRET_KEY = "dev-only-secret-key"

# --- Photos + Gemini OCR ---
PHOTOS_BUCKET = os.getenv("PHOTOS_BUCKET", "be-water-photos")
GEMINI_API_KEY = _FLASK_CFG.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

# Nicknames whose uploads go through the paid studio treatment (image
# generation has no free tier). Everyone else keeps the free OCR prefill
# and their raw photo. Comma-separated env so admins can be added without
# a code change.
ADMIN_NICKNAMES = {
    n.strip().lower()
    for n in os.getenv("BEWATER_ADMINS", "jorgelillo").split(",")
    if n.strip()
}

# --- Google Sign-In (admin + future public login) ---
# Empty until the OAuth client exists (see docs/operations.md runbook):
# the button hides and /admin returns 404, so shipping without it is safe.
GOOGLE_CLIENT_ID = _FLASK_CFG.get("google_client_id") or os.getenv(
    "GOOGLE_CLIENT_ID", ""
)
# Google-verified emails allowed into /admin (comma-separated env).
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.getenv("BEWATER_ADMIN_EMAILS", "").split(",")
    if e.strip()
}

# --- Telegram (catalog-sync notifications) ---
TELEGRAM_BOT_TOKEN = _FLASK_CFG.get("telegram_bot_token", "")
TELEGRAM_CHAT_ID = _FLASK_CFG.get("telegram_chat_id", "")

# --- Deployed version metadata (short SHA, 7 chars) ---
GIT_COMMIT = os.getenv("GIT_COMMIT", "local")
DEPLOY_TIME = os.getenv("DEPLOY_TIME", "")

# --- Canonical base URL for SEO tags (empty until there is a public domain) ---
BASE_URL = os.getenv("BASE_URL", "")
