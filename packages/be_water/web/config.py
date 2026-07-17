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

# --- Deployed version metadata (short SHA, 7 chars) ---
GIT_COMMIT = os.getenv("GIT_COMMIT", "local")
DEPLOY_TIME = os.getenv("DEPLOY_TIME", "")

# --- Canonical base URL for SEO tags (empty until there is a public domain) ---
BASE_URL = os.getenv("BASE_URL", "")
