import os
import sys

from dotenv import load_dotenv

# Pulls vars from a local .env when present (used for local dev).
load_dotenv()

# --- Firestore ---
# be_water deploys to its own GCP project; core.sdk.firestore honours this.
os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

# --- Application secrets ---
# Refuse to start without a SECRET_KEY in production (session cookie signing).
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if "pytest" in sys.modules:
        SECRET_KEY = "pytest-secret-key-not-for-prod"
    elif os.getenv("K_SERVICE"):  # only enforce on Cloud Run
        raise RuntimeError(
            "SECRET_KEY env var is required; refusing to start with a default."
        )
    else:
        SECRET_KEY = "dev-only-secret-key"

# --- Deployed version metadata (short SHA, 7 chars) ---
GIT_COMMIT = os.getenv("GIT_COMMIT", "local")
DEPLOY_TIME = os.getenv("DEPLOY_TIME", "")

# --- Canonical base URL for SEO tags (empty until there is a public domain) ---
BASE_URL = os.getenv("BASE_URL", "")
